# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from urllib.error import HTTPError

import rich.repr

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import get_url_and_parse_html_hrefs
from utils import setup_logging

log: logging.Logger = setup_logging("ubuntu")


@rich.repr.auto
class Ubuntu(DistroBaseInfo):
	arches: list["UbuntuArchInfo"]

	# Read from environment var RELEASE, or use default.
	release: string
	mirror: string

	def __init__(self, release, mirror):
		self.release = release
		self.mirror = mirror

		super().__init__(
			arches=[
				UbuntuArchInfo(distro=self, docker_slug="arm64", slug="arm64"),
				UbuntuArchInfo(distro=self, docker_slug="amd64", slug="amd64")
			],
			default_oci_ref_disk="ubuntu-cloud-container-disk",
			default_oci_ref_kernel="ubuntu-cloud-kernel-kv"
		)

	def handle_extract_kernel_initrd(self, arch, nbd_counter):
		log.warning("Ubuntu has a single partition qcow2, so we need to extract from partition 1, not 2.")
		arch.extract_kernel_initrd_from_qcow2(
			nbd_counter, partition_num=1,
			vmlinuz_glob="boot/vmlinuz-*", initramfs_glob="boot/initrd.img-*"
		)

	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
		self.oci_tag_version = self.release + "-" + self.version
		self.oci_tag_latest = self.release + "-latest"

	def slug(self) -> string:
		return f"ubuntu-{self.release}"

	def kernel_cmdline(self) -> list[string]:
		return ["root=LABEL=cloudimg-rootfs", "ro"]


@rich.repr.auto
class UbuntuArchInfo(DistroBaseArchInfo):

	distro: "Ubuntu"
	index_url: string = None
	all_hrefs: list[string]
	qcow2_hrefs: list[string]

	def grab_version(self):
		indexes_to_try = [f"{self.distro.mirror}/{self.distro.release}/"]

		# Log the indexes
		log.info(f"Trying indexes: {indexes_to_try}")

		for index_url in indexes_to_try:
			try:
				self.index_url = index_url
				self.all_hrefs = get_url_and_parse_html_hrefs(self.index_url)
				break
			except HTTPError as e:
				continue

		if self.index_url is None:
			raise Exception(f"Could not find valid index for {self.slug}")

		datey_hrefs = list(set([  # make unique, there's duplicate links
			href[:-1] for href in self.all_hrefs  # remove trailing slash
			if href.startswith('20') and href.endswith("/")  # won't work in 22nd century
		]))
		log.debug(f"datey_hrefs: {datey_hrefs}")

		# sort ascending, hope for the best; Python sort mutates the list
		datey_hrefs.sort()

		# get the last one
		self.version = datey_hrefs[-1]

		log.info(f"self.version: '{self.version}' out of {len(datey_hrefs)} possible.")

		self.index_url = self.index_url + self.version + "/"
		log.info(f"self.index_url: {self.index_url}")

		self.all_hrefs = get_url_and_parse_html_hrefs(self.index_url)

		# log.info(f"self.all_hrefs: {self.all_hrefs}")

		self.qcow2_hrefs = list(set([  # make unique, there's duplicate links
			href for href in self.all_hrefs
			if href.endswith(".img") and ("-" + self.slug + ".") in href
		]))

		# Make sure there is only one qcow2 href.
		if len(self.qcow2_hrefs) != 1:
			raise Exception(f"Found {len(self.qcow2_hrefs)} qcow2 hrefs for {self.slug}: {self.qcow2_hrefs}")

		log.info(f"self.qcow2_hrefs: {self.qcow2_hrefs}")

		qcow2_url_filename = self.qcow2_hrefs[0]
		qcow2_basename = os.path.basename(qcow2_url_filename)[:-len(".img")]

		self.qcow2_filename = f"{qcow2_basename}-{self.version}.qcow2"
		self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
		self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

		self.qcow2_url = self.index_url + qcow2_url_filename
