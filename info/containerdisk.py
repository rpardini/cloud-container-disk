# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import string
from abc import abstractmethod

import rich.repr
from rich.syntax import Syntax

from utils import global_console
from utils import setup_logging
from utils import shell
from utils import shell_passthrough

log: logging.Logger = setup_logging("containerDisk")


# @TODO: the LABELs need a lot of work, info has to be passed down from the distro to the arch to the image
# @TODO: also, store the original vmlinuz/initrd filenames (not qcow2-derived)

# @TODO: refactor, stop doing the same stuff twice for latest and versioned tags

@rich.repr.auto
class BaseOCISingleArchImage:
	oci_ref: string
	tag_version: string
	tag_latest: string
	docker_arch: string

	def __init__(self, oci_ref, tag_version, tag_latest, docker_arch):
		self.oci_ref = oci_ref
		self.tag_version = tag_version + "-" + docker_arch
		self.tag_latest = tag_latest + "-" + docker_arch
		self.docker_arch = docker_arch

	def build(self):
		log.info(f"Building {self.full_ref_version} and {self.full_ref_latest}")
		contents = self.dockerfile()

		global_console().print(Syntax(contents, "dockerfile"))

		# write contents to "Dockerfile"
		with open("Dockerfile", "w") as f:
			f.write(contents)

		ignores = self.dockerignore()
		global_console().print(Syntax(ignores, "dockerignore"))

		# write ignores to ".dockerignore"
		with open(".dockerignore", "w") as f:
			f.write(ignores)

		# build the image
		shell_passthrough(["docker", "build", "-t", f"{self.full_ref_version}", "."])

		# tag the image as latest
		shell_passthrough(["docker", "tag", f"{self.full_ref_version}", f"{self.full_ref_latest}"])

	@property
	def full_ref_version(self):
		return f"{self.oci_ref}:{self.tag_version}"

	@property
	def full_ref_latest(self):
		return f"{self.oci_ref}:{self.tag_latest}"

	def push(self):
		# push the image & the latest tag
		shell_passthrough(["docker", "push", f"{self.full_ref_version}"])
		shell_passthrough(["docker", "push", f"{self.full_ref_latest}"])

	@abstractmethod
	def dockerfile(self):
		pass

	@abstractmethod
	def dockerignore(self):
		pass


@rich.repr.auto
class ArchContainerKernelImage(BaseOCISingleArchImage):
	def dockerignore(self):
		return f"""*
!{self.kernel_filename}
!{self.initramfs_filename}
"""

	kernel_filename: string
	initramfs_filename: string

	def __init__(self, oci_ref, tag_version, tag_latest, docker_arch, kernel_filename, initramfs_filename):
		super().__init__(oci_ref, tag_version, tag_latest, docker_arch)
		self.kernel_filename = kernel_filename
		self.initramfs_filename = initramfs_filename

	def dockerfile(self):
		return f"""FROM scratch
ADD --chown=107:107 {self.kernel_filename} /boot/vmlinuz
ADD --chown=107:107 {self.initramfs_filename} /boot/initrd
LABEL org.opencontainers.image.description="Cloud image kernel and initrd image version '{self.tag_version}' for arch {self.docker_arch} containing {self.kernel_filename} as /boot/vmlinuz and {self.initramfs_filename} as /boot/initrd"
"""


@rich.repr.auto
class ArchContainerDiskImage(BaseOCISingleArchImage):
	qcow2_filename: string

	def __init__(self, oci_ref, tag_version, tag_latest, docker_arch, qcow2_filename):
		super().__init__(oci_ref, tag_version, tag_latest, docker_arch)
		self.qcow2_filename = qcow2_filename

	def dockerfile(self):
		return f"""FROM scratch
ADD --chown=107:107 {self.qcow2_filename} /disk/{self.qcow2_filename}
LABEL org.opencontainers.image.description="Cloud containerDisk qcow2 version '{self.tag_version}' for arch {self.docker_arch} containing /disk/{self.qcow2_filename}"
"""

	def dockerignore(self):
		return f"""*
!{self.qcow2_filename}
"""


class MultiArchImage:
	type: string
	arch_images: dict[string, BaseOCISingleArchImage]
	oci_ref: string
	tag_version: string
	tag_latest: string

	def __init__(self, type, oci_ref, tag_version, tag_latest):
		self.type = type
		self.oci_ref = oci_ref
		self.tag_version = tag_version
		self.tag_latest = tag_latest
		self.arch_images = {}

	@property
	def full_ref_version(self):
		return f"{self.oci_ref}:{self.tag_version}"

	@property
	def full_ref_latest(self):
		return f"{self.oci_ref}:{self.tag_latest}"

	def create_disk_image(self, arch: string, qcow2_filename: string):
		self.arch_images[arch] = ArchContainerDiskImage(
			self.oci_ref, self.tag_version, self.tag_latest, arch,
			qcow2_filename)

	def create_kernel_image(self, arch: string, kernel_filename: string, initramfs_filename: string):
		self.arch_images[arch] = ArchContainerKernelImage(
			self.oci_ref, self.tag_version, self.tag_latest, arch,
			kernel_filename, initramfs_filename)

	def build(self):
		log.info(f"Building ({self.type}): {self.full_ref_version} and {self.full_ref_latest}")
		for arch, arch_image in self.arch_images.items():
			log.info(
				f"Building ({self.type}): {self.full_ref_version} and {self.full_ref_latest} for {arch}")
			arch_image.build()

	def push(self):
		log.info(f"Pushing ({self.type}): {self.full_ref_version} and {self.full_ref_latest}")
		for arch, arch_image in self.arch_images.items():
			log.info(
				f"Pushing ({self.type}): {self.full_ref_version} and {self.full_ref_latest} for {arch}")
			arch_image.push()

		# Create the manifest for the versioned tag
		log.info(f"Creating manifest for {self.full_ref_version}")
		shell(
			["docker", "manifest", "create", "--amend", f"{self.full_ref_version}"] + [
				f"{self.full_ref_version}-{arch}" for arch in self.arch_images.keys()])

		for arch, arch_image in self.arch_images.items():
			log.info(f"Annotating {self.full_ref_version}-{arch} as {arch}")
			shell_passthrough(
				["docker", "manifest", "annotate", f"{self.full_ref_version}",
				 f"{self.full_ref_version}-{arch}", "--arch", arch])

		# Create the manifest for the latest tag
		log.info(f"Creating manifest for {self.full_ref_latest}")
		shell_passthrough(
			["docker", "manifest", "create", "--amend", f"{self.full_ref_latest}"] +
			[f"{self.full_ref_latest}-{arch}" for arch in self.arch_images.keys()]
		)

		for arch, arch_image in self.arch_images.items():
			log.info(f"Annotating {self.full_ref_latest}-{arch} as {arch}")
			shell_passthrough([
				"docker", "manifest", "annotate", f"{self.full_ref_latest}",
				f"{self.full_ref_latest}-{arch}", "--arch", arch])

		# push the manifest for the versioned tag
		log.info(f"Pushing manifest for {self.full_ref_version}")
		shell_passthrough(["docker", "manifest", "push", f"{self.full_ref_version}"])

		# push the manifest for the latest tag
		log.info(f"Pushing manifest for {self.full_ref_latest}")
		shell_passthrough(["docker", "manifest", "push", f"{self.full_ref_latest}"])
