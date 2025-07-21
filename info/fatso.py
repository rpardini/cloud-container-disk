# Pay attention, work step by step, use modern (3.13) Python syntax and features.
import logging
import os
import string

import rich.repr

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import setup_logging, GitHubReleaseReleaseAssets

log: logging.Logger = setup_logging("fatso")


@rich.repr.auto
class Fatso(DistroBaseInfo):
    arches: list["FatsoArchInfo"]

    flavor: str
    fid: str

    def __init__(self, flavor, fid):
        self.flavor = flavor
        self.fid = fid

        super().__init__(
            arches=[
                FatsoArchInfo(distro=self, docker_slug="arm64", slug="aarch64"),
                FatsoArchInfo(distro=self, docker_slug="amd64", slug="x86_64"),
            ],
            default_oci_ref_disk="fatso-cloud-container-disk",
            default_oci_ref_kernel="fatso-cloud-kernel-kv",
        )

    def set_version_from_arch_versions(self, arch_versions: set[str]) -> string:
        self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
        self.oci_tag_version = f"{self.fid}-{self.version}"
        self.oci_tag_latest = f"{self.fid}-latest"

    def slug(self) -> string:
        return f"fatso-{self.fid}"

    def kernel_cmdline(self) -> list[str]:
        return ["root=PARTLABEL=rootfs", "ro"]  # @TODO: probably wrong

    def boot_dir_prefix(self) -> string:
        log.info(f"Fatso {self.release} uses rootfs booting at partition 3 and kernel in boot/ directory")
        return "boot/"


@rich.repr.auto
class FatsoArchInfo(DistroBaseArchInfo):
    distro: "Fatso"
    index_url: string = None
    all_hrefs: list[str]
    qcow2_hrefs: list[str]

    gh_release_version: string = None
    gh_asset_filename: string = None
    gh_asset_dl_url: string = None

    def boot_partition_num(self) -> int:
        log.info(
            f"Fatso {self.distro.flavor} uses rootfs booting at partition 3 (2 for arm64) and kernel in boot/ directory"
        )
        if self.docker_slug == "arm64":
            return 2  # esp + rootfs
        return 3  # "bios" partition, esp, rootfs

    def grab_version(self):
        self.gh_release_version = None
        self.gh_asset_filename = None
        self.gh_asset_dl_url = None
        searched_variant_token = f"{self.distro.flavor}_{self.docker_slug}.qcow2.gz"

        ghra = GitHubReleaseReleaseAssets(github_org_repo="k8s-avengers/fatso-images", release_tag=None)
        release_info_assets = ghra.get_release_assets()
        repo_release_assets = release_info_assets["assets"]
        repo_release = release_info_assets["repo_release"]

        log.debug(f"repo_release_assets: {repo_release_assets}")
        for repo_release_asset in repo_release_assets:
            asset_fn = repo_release_asset.name
            asset_dl_url = repo_release_asset.browser_download_url
            log.debug(f"Trying repo_release_asset '{asset_fn}' ")
            if searched_variant_token not in asset_fn:
                log.debug(
                    f"Skipping repo_release_asset '{asset_fn}' because it does not contain '{searched_variant_token}'"
                )
                continue
            # If we got this far, we've the correct qcow2.xz asset.
            log.info(f"Found! repo_release_asset '{asset_fn}' ")
            self.gh_asset_filename = asset_fn
            self.gh_asset_dl_url = asset_dl_url
            self.gh_release_version = repo_release.tag_name

        if self.gh_release_version is None:
            raise Exception(f"Could not find valid release for {self.slug}")
        if self.gh_asset_filename is None:
            raise Exception(f"Could not find valid asset for {self.slug}")
        if self.gh_asset_dl_url is None:
            raise Exception(f"Could not find valid asset for {self.slug}")

        qcow2_url_filename = self.gh_asset_filename
        qcow2_basename = os.path.basename(qcow2_url_filename)[: -len(".img.qcow2.gz")]

        self.qcow2_is_xz = True # @TODO: gz, not xz
        self.qcow2_filename = f"{qcow2_basename}.qcow2"
        self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
        self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

        self.qcow2_url = self.gh_asset_dl_url
        self.version = self.gh_release_version
