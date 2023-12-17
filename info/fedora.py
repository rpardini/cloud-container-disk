# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from urllib.error import HTTPError

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import get_url_and_parse_html_hrefs
from utils import setup_logging

log: logging.Logger = setup_logging("fedora")


class Fedora(DistroBaseInfo):
	arches: list["FedoraArchInfo"]

	# Read from environment var RELEASE, or use default.
	release: string
	mirror: string

	def __init__(self, release, mirror):
		self.release = release
		self.mirror = mirror

		super().__init__(
			arches=[
				FedoraArchInfo(distro=self, docker_slug="arm64", slug="aarch64"),
				FedoraArchInfo(distro=self, docker_slug="amd64", slug="x86_64")
			],
			default_oci_ref_disk="fedora-cloud-container-disk",
			default_oci_ref_kernel="fedora-cloud-kernel-kv"
		)

	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
		self.oci_tag_version = self.release + "-" + self.version
		self.oci_tag_latest = self.release + "-latest"


class FedoraArchInfo(DistroBaseArchInfo):
	distro: "Fedora"
	index_url: string = None
	all_hrefs: list[string]
	qcow2_hrefs: list[string]

	def grab_version(self):
		indexes_to_try = [
			f"{self.distro.mirror}/linux/releases/{self.distro.release}/Cloud/{self.slug}/images/"
		]

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

		self.qcow2_hrefs = [
			href for href in self.all_hrefs
			if href.endswith(".qcow2") and ".latest." not in href
		]

		# Make sure there is only one qcow2 href.
		if len(self.qcow2_hrefs) != 1:
			raise Exception(f"Found {len(self.qcow2_hrefs)} qcow2 hrefs for {self.slug}: {self.qcow2_hrefs}")

		self.qcow2_filename = self.qcow2_hrefs[0]
		qcow2_basename = os.path.basename(self.qcow2_filename)
		self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
		self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

		# Parse version out of the qcow2_href. very fragile.
		dash_split = self.qcow2_filename.split("-")
		log.info(f"dash_split: {dash_split}")

		release_from_split = dash_split[3]
		assert release_from_split == self.distro.release, f"release_from_split: {release_from_split} != self.distro.release: {self.distro.release}"

		self.version = dash_split[4].replace(f".{self.slug}.qcow2", "")

		# full url
		self.qcow2_url = self.index_url + self.qcow2_filename
