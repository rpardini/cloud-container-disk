# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from abc import abstractmethod

from utils import DevicePathMounter
from utils import NBDImageMounter
from utils import setup_logging
from utils import shell
from utils import shell_passthrough

log: logging.Logger = setup_logging("distro_arch")


class DistroBaseArchInfo:
	distro: object  # DistroBaseInfo
	docker_slug: string
	slug: string
	version: string = None
	qcow2_url: string = None
	qcow2_filename: string = None  # filename on disk
	vmlinuz_final_filename: string = None
	initramfs_final_filename: string = None
	qcow2_is_xz: bool

	@abstractmethod
	def grab_version(self) -> string:
		pass

	def __init__(self, distro, docker_slug, slug):
		self.distro = distro
		self.docker_slug = docker_slug
		self.slug = slug
		self.qcow2_is_xz = False

	def download_arch_qcow2(self):
		log.info(f"Architecture: {self.slug}: {self}")
		log.info(f"Downloading {self.qcow2_url} to {self.qcow2_filename}")
		# Only download if filename is not already downloaded.
		if not os.path.exists(self.qcow2_filename):
			log.info(f"Downloading {self.qcow2_url} to {self.qcow2_filename}")

			# Use the shell to do the download, using curl -o's output filename option. -L follows redirects.
			down_output_fn = f"{self.qcow2_filename}.tmp"

			if self.qcow2_is_xz:
				log.info(f"Adding .xz extension to {down_output_fn}")
				down_output_fn += ".xz"

			shell_passthrough([f"curl", "-L", "-o", down_output_fn, f"{self.qcow2_url}"])
			log.info(f"Downloaded {self.qcow2_url} to {down_output_fn}")

			if self.qcow2_is_xz:  # uncompress, using pixz
				log.info(f"Uncompressing {down_output_fn} to {self.qcow2_filename}")
				shell_passthrough([f"pixz", "-d", f"{down_output_fn}"])
				down_output_fn = down_output_fn[:-3]  # # remove the .xz extension from the filename

			# Rename the temp file to the final filename.
			log.info(f"Renaming {down_output_fn} to {self.qcow2_filename}")
			os.rename(f"{down_output_fn}", self.qcow2_filename)
		else:
			log.info(f"Skipping download, {self.qcow2_filename} already exists")

	def extract_kernel_initrd_from_qcow2(
			self, nbd_counter, vmlinuz_glob=None, initramfs_glob=None):
		if initramfs_glob is None:
			initramfs_glob = ["initramfs-*", "initrd.img-*"]
		if vmlinuz_glob is None:
			vmlinuz_glob = ["vmlinuz-*"]
		if os.path.exists(self.vmlinuz_final_filename) and os.path.exists(self.initramfs_final_filename):
			log.info(
				f"Skipping extraction, {self.vmlinuz_final_filename} and {self.initramfs_final_filename} already exist")
			return

		with NBDImageMounter(nbd_counter, self.qcow2_filename) as nbd:
			with DevicePathMounter(nbd.nbd_device, self.boot_partition_num(), f"mnt-{self.qcow2_filename}") as mp:
				vmlinuz_filename = mp.glob_non_rescue(self.boot_dir_prefix(), vmlinuz_glob)
				log.info(f"vmlinuz_filename: {vmlinuz_filename}")
				shell(["cp", "-v", f"{mp.mountpoint}/{vmlinuz_filename}", f"{self.vmlinuz_final_filename}"])

				initramfs_filename = mp.glob_non_rescue(self.boot_dir_prefix(), initramfs_glob)
				log.info(f"initramfs_filename: {initramfs_filename}")
				shell(["cp", "-v", f"{mp.mountpoint}/{initramfs_filename}", f"{self.initramfs_final_filename}"])

	def kernel_cmdline(self) -> list[string]:
		if self.docker_slug == "arm64":
			return ["console=ttyAMA0"]
		if self.docker_slug == "amd64":
			return ["console=ttyS0", "earlyprintk=ttyS0"]
		raise Exception(f"Unknown docker_slug: {self.docker_slug}")

	def boot_partition_num(self):
		log.info("Using default arch boot_partition_num, delegating to distro...")
		# noinspection PyUnresolvedReferences
		return self.distro.boot_partition_num()

	def boot_dir_prefix(self):
		log.info("Using default arch boot_dir_prefix, delegating to distro...")
		# noinspection PyUnresolvedReferences
		return self.distro.boot_dir_prefix()

	@property
	def qemu_machine_type(self):
		if self.docker_slug == "arm64":
			return "virt"
		if self.docker_slug == "amd64":
			return "q35"
		raise Exception(f"Unknown docker_slug: {self.docker_slug}")
