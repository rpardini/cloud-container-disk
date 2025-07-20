# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from urllib.error import HTTPError

from distro import DistroBaseInfo
from distro_arch import DistroBaseArchInfo
from utils import get_url_and_parse_html_hrefs
from utils import setup_logging

log: logging.Logger = setup_logging("rocky")


class Rocky(DistroBaseInfo):
    def slug(self) -> string:
        return f"rocky-{self.ROCKY_RELEASE}"

    def kernel_cmdline(self) -> list[string]:
        return [
            "root=/dev/mapper/rocky-root",
            "rd.lvm.lv=rocky/root",
            "ro",
            "no_timer_check",
            "net.ifnames=0",
            "crashkernel=auto",
        ]

    arches: list["RockyArchInfo"]

    # Read from environment var RELEASE, or use default.
    ROCKY_RELEASE: string
    ROCKY_VARIANT: string
    ROCKY_MIRROR: string
    ROCKY_VAULT_MIRROR: string

    def __init__(self, rocky_version, rocky_variant, rocky_mirror, rocky_vault_mirror):
        self.ROCKY_RELEASE = rocky_version
        self.ROCKY_VARIANT = rocky_variant
        self.ROCKY_MIRROR = rocky_mirror
        self.ROCKY_VAULT_MIRROR = rocky_vault_mirror

        super().__init__(
            arches=[
                RockyArchInfo(distro=self, docker_slug="arm64", slug="aarch64"),
                RockyArchInfo(distro=self, docker_slug="amd64", slug="x86_64"),
            ],
            default_oci_ref_disk="rocky-cloud-container-disk",
            default_oci_ref_kernel="rocky-cloud-kernel-kv",
        )

    def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
        self.version = "-".join(arch_versions)  # just join all distinct versions, hopefully there is only one
        self.oci_tag_version = self.ROCKY_RELEASE + "-" + self.version
        self.oci_tag_latest = self.ROCKY_RELEASE + "-latest"


class RockyArchInfo(DistroBaseArchInfo):
    distro: "Rocky"
    index_url: string = None
    all_hrefs: list[string]
    qcow2_hrefs: list[string]

    def grab_version(self):
        indexes_to_try = [
            f"{self.distro.ROCKY_MIRROR}/{self.distro.ROCKY_RELEASE}/images/{self.slug}/",
            f"{self.distro.ROCKY_VAULT_MIRROR}/{self.distro.ROCKY_RELEASE}/images/{self.slug}/",
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
            href
            for href in self.all_hrefs
            if href.endswith(".qcow2") and ".latest." not in href and self.distro.ROCKY_VARIANT in href
        ]

        # Make sure there is only one qcow2 href.
        if len(self.qcow2_hrefs) != 1:
            raise Exception(f"Found {len(self.qcow2_hrefs)} qcow2 hrefs for {self.slug}: {self.qcow2_hrefs}")

        self.qcow2_filename = self.qcow2_hrefs[0]
        qcow2_basename = os.path.basename(self.qcow2_filename)[: -len(".qcow2")]
        self.vmlinuz_final_filename = f"{qcow2_basename}.vmlinuz"
        self.initramfs_final_filename = f"{qcow2_basename}.initramfs"

        # Parse version out of the qcow2_href. very fragile.
        dash_split = self.qcow2_filename.split("-")
        self.version = dash_split[4] + "-" + dash_split[5].replace(f".{self.slug}.qcow2", "")

        # full url
        self.qcow2_url = self.index_url + self.qcow2_filename
