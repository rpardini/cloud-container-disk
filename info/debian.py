# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from urllib.error import HTTPError

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import get_url_and_parse_html_hrefs
from utils import setup_logging

log: logging.Logger = setup_logging("debian")


class Debian(DistroBaseInfo):
	def slug(self) -> string:
		return f"debian-{self.release}"

	def kernel_cmdline(self) -> list[string]:
		return ["root=/dev/vda1", "ro"]  # bad, but Debian does not label either the partition or the filesystem, so we've to hardcode it

	arches: list["DebianArchInfo"]

	# Read from environment var RELEASE, or use default.
	release: string
	variant: string
	mirror: string

	def __init__(self, release, variant, mirror):
		self.release = release
		self.variant = variant
		self.mirror = mirror

		super().__init__(
			arches=[
				DebianArchInfo(distro=self, docker_slug="arm64", slug="arm64"),
				DebianArchInfo(distro=self, docker_slug="amd64", slug="amd64")
			],
			default_oci_ref_disk="debian-cloud-container-disk",
			default_oci_ref_kernel="debian-cloud-kernel-kv"
		)

	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
		self.oci_tag_version = self.release + "-" + self.version
		self.oci_tag_latest = self.release + "-latest"

	def boot_partition_num(self) -> int:
		log.info("Debian: Using partition n. 1 (rootfs) for booting, with boot/ directory.")
		return 1

	def boot_dir_prefix(self) -> string:
		log.info("Debian: Using partition n. 1 (rootfs) for booting, with boot/ directory.")
		return "boot/"


class DebianArchInfo(DistroBaseArchInfo):
	distro: "Debian"
	index_url: string = None
	all_hrefs: list[string]
	qcow2_hrefs: list[string]

	def grab_version(self):
		indexes_to_try = [f"{self.distro.mirror}/{self.distro.release}/daily/"]

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

		self.qcow2_hrefs = list(set([  # make unique, there's duplicate links
			href for href in self.all_hrefs
			if href.endswith(".qcow2") and ("-" + self.slug + "-") in href and ("-" + self.distro.variant + "-") in href
		]))

		# Make sure there is only one qcow2 href.
		if len(self.qcow2_hrefs) != 1:
			raise Exception(f"Found {len(self.qcow2_hrefs)} qcow2 hrefs for {self.slug}: {self.qcow2_hrefs}")

		self.qcow2_filename = self.qcow2_hrefs[0]
		qcow2_basename = os.path.basename(self.qcow2_filename)[:-len(".qcow2")]
		self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
		self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

		self.qcow2_url = self.index_url + self.qcow2_filename
