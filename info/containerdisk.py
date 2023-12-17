# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import string
from abc import abstractmethod

from utils import shell
from utils import shell_passthrough


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
		print(f"Building {self.oci_ref}:{self.tag_version} and {self.oci_ref}:{self.tag_latest}")
		contents = self.dockerfile()
		print(f"contents:\n{contents}")

		# write contents to "Dockerfile"
		with open("Dockerfile", "w") as f:
			f.write(contents)

		ignores = self.dockerignore()
		print(f"ignores:\n{ignores}")

		# write ignores to ".dockerignore"
		with open(".dockerignore", "w") as f:
			f.write(ignores)

		# build the image
		shell_passthrough(["docker", "build", "-t", f"{self.oci_ref}:{self.tag_version}", "."])

		# tag the image as latest
		shell_passthrough(["docker", "tag", f"{self.oci_ref}:{self.tag_version}", f"{self.oci_ref}:{self.tag_latest}"])

	def push(self):
		# push the image & the latest tag
		shell_passthrough(["docker", "push", f"{self.oci_ref}:{self.tag_version}"])
		shell_passthrough(["docker", "push", f"{self.oci_ref}:{self.tag_latest}"])

	@abstractmethod
	def dockerfile(self):
		pass

	@abstractmethod
	def dockerignore(self):
		pass


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
		return f"""
		FROM scratch
		ADD --chown=107:107 {self.kernel_filename} /boot/vmlinuz
		ADD --chown=107:107 {self.initramfs_filename} /boot/initrd
		"""


class ArchContainerDiskImage(BaseOCISingleArchImage):
	qcow2_filename: string

	def __init__(self, oci_ref, tag_version, tag_latest, docker_arch, qcow2_filename):
		super().__init__(oci_ref, tag_version, tag_latest, docker_arch)
		self.qcow2_filename = qcow2_filename

	def dockerfile(self):
		return f"""
		FROM scratch
		ADD --chown=107:107 {self.qcow2_filename} /disk/{self.qcow2_filename}
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

	def create_disk_image(self, arch: string, qcow2_filename: string):
		self.arch_images[arch] = ArchContainerDiskImage(
			self.oci_ref, self.tag_version, self.tag_latest, arch,
			qcow2_filename)

	def create_kernel_image(self, arch: string, kernel_filename: string, initramfs_filename: string):
		self.arch_images[arch] = ArchContainerKernelImage(
			self.oci_ref, self.tag_version, self.tag_latest, arch,
			kernel_filename, initramfs_filename)

	def build(self):
		print(f"Building ({self.type}): {self.oci_ref}:{self.tag_version} and {self.oci_ref}:{self.tag_latest}")
		for arch, arch_image in self.arch_images.items():
			print(
				f"Building ({self.type}): {self.oci_ref}:{self.tag_version} and {self.oci_ref}:{self.tag_latest} for {arch}")
			arch_image.build()

	def push(self):
		print(f"Pushing ({self.type}): {self.oci_ref}:{self.tag_version} and {self.oci_ref}:{self.tag_latest}")
		for arch, arch_image in self.arch_images.items():
			print(
				f"Pushing ({self.type}): {self.oci_ref}:{self.tag_version} and {self.oci_ref}:{self.tag_latest} for {arch}")
			arch_image.push()

		# Create the manifest for the versioned tag
		print(f"Creating manifest for {self.oci_ref}:{self.tag_version}")
		shell(
			["docker", "manifest", "create", "--amend", f"{self.oci_ref}:{self.tag_version}"] + [
				f"{self.oci_ref}:{self.tag_version}-{arch}" for arch in self.arch_images.keys()])

		for arch, arch_image in self.arch_images.items():
			print(f"Annotating {self.oci_ref}:{self.tag_version}-{arch} as {arch}")
			shell_passthrough(
				["docker", "manifest", "annotate", f"{self.oci_ref}:{self.tag_version}",
				 f"{self.oci_ref}:{self.tag_version}-{arch}", "--arch", arch])

		# Create the manifest for the latest tag
		print(f"Creating manifest for {self.oci_ref}:{self.tag_latest}")
		shell_passthrough(
			["docker", "manifest", "create", "--amend", f"{self.oci_ref}:{self.tag_latest}"] +
			[f"{self.oci_ref}:{self.tag_latest}-{arch}" for arch in self.arch_images.keys()]
		)

		for arch, arch_image in self.arch_images.items():
			print(f"Annotating {self.oci_ref}:{self.tag_latest}-{arch} as {arch}")
			shell_passthrough([
				"docker", "manifest", "annotate", f"{self.oci_ref}:{self.tag_latest}",
				f"{self.oci_ref}:{self.tag_latest}-{arch}", "--arch", arch])

		# push the manifest for the versioned tag
		print(f"Pushing manifest for {self.oci_ref}:{self.tag_version}")
		shell_passthrough(["docker", "manifest", "push", f"{self.oci_ref}:{self.tag_version}"])

		# push the manifest for the latest tag
		print(f"Pushing manifest for {self.oci_ref}:{self.tag_latest}")
		shell_passthrough(["docker", "manifest", "push", f"{self.oci_ref}:{self.tag_latest}"])
