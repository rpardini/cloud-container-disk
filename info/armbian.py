# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string

import rich.repr
from github import Github

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import setup_logging

log: logging.Logger = setup_logging("armbian")


@rich.repr.auto
class Armbian(DistroBaseInfo):
	arches: list["ArmbianArchInfo"]

	# Read from environment var RELEASE, or use default.
	release: string
	branch: string
	variant: string

	def __init__(self, release, branch):
		self.release = release
		self.branch = branch
		self.variant = "metadata-cloud"

		super().__init__(
			arches=[
				ArmbianArchInfo(distro=self, docker_slug="arm64", slug="Uefi-arm64"),
				ArmbianArchInfo(distro=self, docker_slug="amd64", slug="Uefi-x86")
			],
			default_oci_ref_disk="armbian-cloud-container-disk",
			default_oci_ref_kernel="armbian-cloud-kernel-kv"
		)

	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
		self.oci_tag_version = self.release + "-" + self.branch + "-" + self.version
		self.oci_tag_latest = self.release + "-" + self.branch + "-latest"

	def slug(self) -> string:
		return f"armbian-{self.release}-{self.branch}"

	def kernel_cmdline(self) -> list[string]:
		return ["root=PARTLABEL=rootfs", "ro"]

	def boot_dir_prefix(self) -> string:
		log.info(f"Armbian {self.release} uses rootfs booting at partition 3 and kernel in boot/ directory")
		return "boot/"


@rich.repr.auto
class ArmbianArchInfo(DistroBaseArchInfo):
	distro: "Armbian"
	index_url: string = None
	all_hrefs: list[string]
	qcow2_hrefs: list[string]

	gh_release_version: string = None
	gh_asset_filename: string = None
	gh_asset_dl_url: string = None

	def boot_partition_num(self) -> int:
		log.info(f"Armbian {self.distro.release} uses rootfs booting at partition 3 (2 for arm64) and kernel in boot/ directory")
		if self.docker_slug == "arm64":
			return 2  # esp + rootfs
		return 3  # "bios" partition, esp, rootfs

	def grab_version(self):
		self.gh_release_version = None
		self.gh_asset_filename = None
		self.gh_asset_dl_url = None

		searched_variant_token = f"-{self.distro.variant}.img"
		searched_slugh_release_branch_tokens = f"{self.slug}_{self.distro.release}_{self.distro.branch}"

		github = Github()
		if os.environ.get("GITHUB_TOKEN", "") != "":
			log.info("Using GITHUB_TOKEN from environment!")
			github = Github(os.environ.get("GITHUB_TOKEN"))
		else:
			log.warning("GITHUB_TOKEN not set in environment, will use anonymous API calls (lower rate limits)!")

		repo = github.get_repo("rpardini/armbian-release")
		log.debug(f"repo: {repo}")
		repo_releases = repo.get_releases().get_page(0)
		log.debug(f"repo_releases: {repo_releases}")
		for repo_release in repo_releases:
			log.debug(f"Trying repo_release '{repo_release.tag_name}' ")
			# get the assets in the release
			repo_release_assets = repo_release.get_assets()
			log.debug(f"repo_release_assets: {repo_release_assets}")
			for repo_release_asset in repo_release_assets:
				asset_fn = repo_release_asset.name
				asset_dl_url = repo_release_asset.browser_download_url
				if not asset_fn.endswith(".qcow2.xz"):
					continue
				log.debug(f"Trying repo_release_asset '{asset_fn}' ")
				if searched_variant_token not in asset_fn:
					log.debug(f"Skipping repo_release_asset '{asset_fn}' because it does not contain '{searched_variant_token}'")
					continue
				if searched_slugh_release_branch_tokens not in asset_fn:
					log.debug(f"Skipping repo_release_asset '{asset_fn}' because it does not contain '{searched_slugh_release_branch_tokens}'")
					continue
				# If we got this far, we've the correct qcow2.xz asset.
				log.info(f"Found! repo_release_asset '{asset_fn}' ")
				self.gh_asset_filename = asset_fn
				self.gh_asset_dl_url = asset_dl_url
				self.gh_release_version = repo_release.tag_name
			break  # @TODO only try the first release for now

		if self.gh_release_version is None:
			raise Exception(f"Could not find valid release for {self.slug}")
		if self.gh_asset_filename is None:
			raise Exception(f"Could not find valid asset for {self.slug}")
		if self.gh_asset_dl_url is None:
			raise Exception(f"Could not find valid asset for {self.slug}")

		qcow2_url_filename = self.gh_asset_filename
		qcow2_basename = os.path.basename(qcow2_url_filename)[:-len(".img.qcow2.xz")]

		self.qcow2_is_xz = True
		self.qcow2_filename = f"{qcow2_basename}.qcow2"
		self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
		self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

		self.qcow2_url = self.gh_asset_dl_url
		self.version = self.gh_release_version
