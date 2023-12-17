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
	qcow2_filename: string = None
	version: string = None
	qcow2_url: string = None
	vmlinuz_final_filename: string = None
	initramfs_final_filename: string = None

	@abstractmethod
	def grab_version(self) -> string:
		pass

	def __init__(self, distro, docker_slug, slug):
		self.distro = distro
		self.docker_slug = docker_slug
		self.slug = slug

	def download_arch_qcow2(self):
		log.info(f"Architecture: {self.slug}: {self}")
		log.info(f"Downloading {self.qcow2_url} to {self.qcow2_filename}")
		# Only download if filename is not already downloaded.
		if not os.path.exists(self.qcow2_filename):
			log.info(f"Downloading {self.qcow2_url} to {self.qcow2_filename}")
			# Use the shell to do the download, using curl -o's output filename option. -L follows redirects.
			shell_passthrough([f"curl", "-L", "-o", f"{self.qcow2_filename}.tmp", f"{self.qcow2_url}"])
			log.info(f"Downloaded {self.qcow2_url} to {self.qcow2_filename}.tmp")

			# Rename the temp file to the final filename.
			log.info(f"Renaming {self.qcow2_filename}.tmp to {self.qcow2_filename}")
			os.rename(f"{self.qcow2_filename}.tmp", self.qcow2_filename)
		else:
			log.info(f"Skipping download, {self.qcow2_filename} already exists")

	def extract_kernel_initrd_from_qcow2(
			self, nbd_counter, vmlinuz_glob="vmlinuz-*", initramfs_glob="initramfs-*", partition_num=2):
		if os.path.exists(self.vmlinuz_final_filename) and os.path.exists(self.initramfs_final_filename):
			log.info(
				f"Skipping extraction, {self.vmlinuz_final_filename} and {self.initramfs_final_filename} already exist")
			return

		with NBDImageMounter(nbd_counter, self.qcow2_filename) as nbd:
			with DevicePathMounter(nbd.nbd_device, partition_num, f"mnt-{self.qcow2_filename}") as mp:
				vmlinuz_filename = mp.glob_non_rescue(vmlinuz_glob)
				log.info(f"vmlinuz_filename: {vmlinuz_filename}")
				shell(["cp", "-v", f"{mp.mountpoint}/{vmlinuz_filename}", f"{self.vmlinuz_final_filename}"])

				initramfs_filename = mp.glob_non_rescue(initramfs_glob)
				log.info(f"initramfs_filename: {initramfs_filename}")
				shell(["cp", "-v", f"{mp.mountpoint}/{initramfs_filename}", f"{self.initramfs_final_filename}"])
