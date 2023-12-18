# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from abc import abstractmethod

from rich.pretty import pprint

from containerdisk import MultiArchImage
from distro_arch import DistroBaseArchInfo
from utils import setup_logging

log: logging.Logger = setup_logging("distro")


class DistroBaseInfo:
	arches: list[DistroBaseArchInfo]
	version: string = None

	oci_ref_disk: string = None
	oci_ref_kernel: string = None

	oci_tag_version: string = None
	oci_tag_latest: string = None

	def __init__(self, arches: list[DistroBaseArchInfo], default_oci_ref_disk: string, default_oci_ref_kernel: string):
		self.arches = arches
		self.version = None
		self.oci_ref_disk = os.environ.get(
			"DISK_OCI_REF", os.environ.get("BASE_OCI_REF", "ghcr.io/rpardini/") + default_oci_ref_disk)
		self.oci_ref_kernel = os.environ.get(
			"KERNEL_OCI_REF", os.environ.get("BASE_OCI_REF", "ghcr.io/rpardini/") + default_oci_ref_kernel)

	@abstractmethod
	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		pass

	def prepare_version(self) -> string:
		version_set: set[string] = set()
		for arch in self.arches:
			log.info("[green]Grabbing version for arch: [bold]%s[/green][/bold]", arch.slug)
			arch.grab_version()
			version_set.add(arch.version)

		log.info(f"version_set: {version_set}")
		pprint(version_set)
		self.set_version_from_arch_versions(version_set)

		# ensure self.version, self.oci_tag_version and self.oci_tag_latest are set
		assert self.version is not None
		assert self.oci_tag_version is not None
		assert self.oci_tag_latest is not None
		# log them pretty, we've a rich-based logger, use markup, color, and positional arguments
		log.info(
			f"version: [bold]{self.version}[/bold] oci_tag_version: [bold]{self.oci_tag_version}[/bold] oci_tag_latest: [bold]{self.oci_tag_latest}[/bold]")

	def grab_arch_versions(self) -> set[string]:
		ret = set()
		for arch in self.arches:
			log.info("Grabbing version for arch: ", arch.slug)
			arch.grab_version()
			ret.add(arch.version)
		return ret

	def download_qcow2(self):
		for arch in self.arches:
			arch.download_arch_qcow2()

	def extract_kernel_initrd(self):
		nbd_counter = 1
		for arch in self.arches:
			nbd_counter = nbd_counter + 1
			self.handle_extract_kernel_initrd(arch, nbd_counter)

	def handle_extract_kernel_initrd(self, arch, nbd_counter):
		arch.extract_kernel_initrd_from_qcow2(nbd_counter)

	def get_oci_image_definitions(self) -> list[MultiArchImage]:
		return [self.get_oci_def_disk(), self.get_oci_def_kernel()]

	def get_oci_def_disk(self) -> MultiArchImage:
		image = MultiArchImage(
			type="disk",
			oci_ref=self.oci_ref_disk,
			tag_version=self.oci_tag_version,
			tag_latest=self.oci_tag_latest
		)
		for arch in self.arches:
			image.create_disk_image(arch.docker_slug, arch.qcow2_filename)
		return image

	def get_oci_def_kernel(self) -> MultiArchImage:
		image = MultiArchImage(
			type="kernel",
			oci_ref=self.oci_ref_kernel,
			tag_version=self.oci_tag_version,
			tag_latest=self.oci_tag_latest
		)
		for arch in self.arches:
			image.create_kernel_image(arch.docker_slug, arch.vmlinuz_final_filename, arch.initramfs_final_filename)
		return image

	def cli_the_whole_shebang(self):
		self.prepare_version()
		self.download_qcow2()
		self.extract_kernel_initrd()

		oci_images: list[MultiArchImage] = [self.get_oci_def_kernel(), self.get_oci_def_disk()]
		for oci_image in oci_images:
			log.info("oci_image: %s", oci_image)
			pprint(oci_image)
			oci_image.build()
			oci_image.push()
			log.info("--------------------------------------------------------------------------------------------")

		log.info("Done.")

	def template_example(self):
		pass