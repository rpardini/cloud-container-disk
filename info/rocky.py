# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import os
import string
from urllib.error import HTTPError
from urllib.request import urlopen

from bs4 import BeautifulSoup

from containerdisk import MultiArchImage
from utils import DevicePathMounter
from utils import NBDImageMounter
from utils import shell

# Read from environment var RELEASE, or use default.
ROCKY_VERSION = os.environ.get("RELEASE", "8")
ROCKY_VARIANT = os.environ.get("VARIANT", "GenericCloud-LVM")

ROCKY_MIRROR = os.environ.get("ROCKY_MIRROR", "https://dl.rockylinux.org/pub/rocky")
ROCKY_VAULT_MIRROR = "https://dl.rockylinux.org/vault/rocky"


# ROCKY_MIRROR = "https://rocky-linux-europe-west4.production.gcp.mirrors.ctrliq.cloud/pub/rocky"


class RockyArchInfo:
	docker_slug: string
	slug: string
	index_url: string = None
	all_hrefs: list[string]
	qcow2_hrefs: list[string]
	qcow2_filename: string = None
	version: string = None
	qcow2_url: string = None
	vmlinuz_final_filename: string = None
	initramfs_final_filename: string = None

	def __init__(self, docker_slug, slug):
		self.docker_slug = docker_slug
		self.slug = slug

		indexes_to_try = [
			f"{ROCKY_MIRROR}/{ROCKY_VERSION}/images/{slug}/",
			f"{ROCKY_VAULT_MIRROR}/{ROCKY_VERSION}/images/{slug}/"
		]

		for index_url in indexes_to_try:
			try:
				self.index_url = index_url
				self.all_hrefs = self.get_index_hrefs(self.index_url)
				break
			except HTTPError as e:
				continue

		if self.index_url is None:
			raise Exception(f"Could not find valid index for {slug}")

		self.qcow2_hrefs = [
			href for href in self.all_hrefs
			if href.endswith(".qcow2") and ".latest." not in href and ROCKY_VARIANT in href
		]

		# Make sure there is only one qcow2 href.
		if len(self.qcow2_hrefs) != 1:
			raise Exception(f"Found {len(self.qcow2_hrefs)} qcow2 hrefs for {slug}: {self.qcow2_hrefs}")

		self.qcow2_filename = self.qcow2_hrefs[0]
		self.vmlinuz_final_filename = f"{self.qcow2_filename}.vmlinuz"
		self.initramfs_final_filename = f"{self.qcow2_filename}.initramfs"

		# Parse version out of the qcow2_href. very fragile.
		dash_split = self.qcow2_filename.split("-")
		self.version = dash_split[4] + "-" + dash_split[5].replace(f".{self.slug}.qcow2", "")

		# full url
		self.qcow2_url = self.index_url + self.qcow2_filename

	def __str__(self):
		return f"docker_slug: {self.docker_slug}, slug: {self.slug}, version: {self.version}, qcow2_url: {self.qcow2_url}"

	def get_index_hrefs(self, index_url):
		with urlopen(index_url) as response:
			# Use beautifulsoup4 to parse the HTML.
			soup = BeautifulSoup(response, "html.parser")
			# Find all the hrefs.
			hrefs = soup.find_all("a")
			# Loop over the hrefs and print them out.
			links = []
			for href in hrefs:
				href_value = href.get("href")
				# skip empty hrefs
				if href_value is None:
					continue
				links.append(href_value)
			return links


class Rocky:
	arches: list[RockyArchInfo]
	ROCKY_FINAL_VERSION: string
	info_amd64: RockyArchInfo
	info_arm64: RockyArchInfo

	def __init__(self):
		self.info_arm64 = RockyArchInfo(docker_slug="arm64", slug="aarch64")
		self.info_amd64 = RockyArchInfo(docker_slug="amd64", slug="x86_64")
		self.arches = [self.info_amd64, self.info_arm64]

		version_set: set[string] = set()
		# Loop over the ROCKY_ARCH_INFO dictionary and print out the slug and listing for each architecture.
		for arch in self.arches:
			print(f"Architecture: {arch.slug}: {arch}")
			version_set.add(arch.version)

		print(f"version_set: {version_set}")

		# Final version: all versions concatenated with "-" together.
		self.ROCKY_FINAL_VERSION = "-".join(version_set)

		print(f"ROCKY_FINAL_VERSION: {self.ROCKY_FINAL_VERSION}")

	def download_qcow2(self):
		for arch in self.arches:
			print(f"Architecture: {arch.slug}: {arch}")
			print(f"Downloading {arch.qcow2_url} to {arch.qcow2_filename}")
			# Only download if filename is not already downloaded.
			if not os.path.exists(arch.qcow2_filename):
				print(f"Downloading {arch.qcow2_url} to {arch.qcow2_filename}")
				# Use the shell to do the download, using curl -o's output filename option.
				os.system(f"curl -o '{arch.qcow2_filename}.tmp' '{arch.qcow2_url}'")
				# Rename the temp file to the final filename.
				os.rename(f"{arch.qcow2_filename}.tmp", arch.qcow2_filename)
			else:
				print(f"Skipping download, {arch.qcow2_filename} already exists")

	def extract_kernel_initrd(self):
		nbd_counter = 1
		for arch in self.arches:
			if os.path.exists(arch.vmlinuz_final_filename) and os.path.exists(arch.initramfs_final_filename):
				print(
					f"Skipping extraction, {arch.vmlinuz_final_filename} and {arch.initramfs_final_filename} already exist")
				continue

			nbd_counter += 1
			with NBDImageMounter(nbd_counter, arch.qcow2_filename) as nbd:
				with DevicePathMounter(nbd.nbd_device, 2, f"mnt-{arch.slug}-{self.ROCKY_FINAL_VERSION}") as mp:
					vmlinuz_filename = mp.glob_non_rescue("vmlinuz-*")
					print(f"vmlinuz_filename: {vmlinuz_filename}")
					shell(["cp", "-v", f"{mp.mountpoint}/{vmlinuz_filename}", f"{arch.vmlinuz_final_filename}"])

					initramfs_filename = mp.glob_non_rescue("initramfs-*")
					print(f"initramfs_filename: {initramfs_filename}")
					shell(["cp", "-v", f"{mp.mountpoint}/{initramfs_filename}", f"{arch.initramfs_final_filename}"])

	def get_oci_def_disk(self) -> MultiArchImage:
		# one for qcow2
		qcow2 = MultiArchImage(
			type="disk",
			oci_ref=os.environ.get("DISK_OCI_REF", "ghcr.io/rpardini/rocky-cloud-container-disk"),
			tag_version=ROCKY_VERSION + "-" + self.ROCKY_FINAL_VERSION,
			tag_latest=ROCKY_VERSION + "-latest"
		)
		qcow2.create_disk_image("amd64", self.info_amd64.qcow2_filename)
		qcow2.create_disk_image("arm64", self.info_arm64.qcow2_filename)
		return qcow2

	def get_oci_def_kernel(self) -> MultiArchImage:
		kernel = MultiArchImage(
			type="kernel",
			oci_ref=os.environ.get("KERNEL_OCI_REF", "ghcr.io/rpardini/rocky-cloud-kernel-kv"),
			tag_version=ROCKY_VERSION + "-" + self.ROCKY_FINAL_VERSION,
			tag_latest=ROCKY_VERSION + "-latest"
		)
		kernel.create_kernel_image(
			"amd64", self.info_amd64.vmlinuz_final_filename,
			self.info_amd64.initramfs_final_filename)
		kernel.create_kernel_image(
			"arm64", self.info_arm64.vmlinuz_final_filename,
			self.info_arm64.initramfs_final_filename)
		return kernel


# one for kernel/initramfs


rocky = Rocky()
rocky.download_qcow2()
rocky.extract_kernel_initrd()

oci_images: list[MultiArchImage] = [rocky.get_oci_def_kernel(), rocky.get_oci_def_disk()]
for oci_image in oci_images:
	print(f"oci_image: {oci_image.type}")
	oci_image.build()
	oci_image.push()
	print("--------------------------------------------------------------------------------------------")

print("Done.")
