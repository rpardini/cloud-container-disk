# Pay attention, work step by step, use modern (3.10+) Python syntax and features.
import logging
import os
import string
from abc import abstractmethod

import jinja2
from rich.pretty import pprint
from rich.pretty import pretty_repr

from containerdisk import MultiArchImage
from distro_arch import DistroBaseArchInfo
from utils import set_gha_output
from utils import setup_logging
from utils import skopeo_inspect_remote_ref

log: logging.Logger = setup_logging("distro")


class DistroBaseInfo:
	arches: list[DistroBaseArchInfo]
	version: string = None

	oci_ref_disk: string = None
	oci_ref_kernel: string = None

	oci_tag_version: string = None
	oci_tag_latest: string = None

	def __init__(self, arches: list[DistroBaseArchInfo], default_oci_ref_disk: string, default_oci_ref_kernel: string):
		self.oci_images: list[MultiArchImage] = None
		self.oci_images_by_type: dict[str, MultiArchImage] = None
		self.arches: list["DistroBaseArchInfo"] = arches
		self.version = None
		self.oci_ref_disk = os.environ.get(
			"DISK_OCI_REF", os.environ.get("BASE_OCI_REF", "ghcr.io/rpardini/") + default_oci_ref_disk)
		self.oci_ref_kernel = os.environ.get(
			"KERNEL_OCI_REF", os.environ.get("BASE_OCI_REF", "ghcr.io/rpardini/") + default_oci_ref_kernel)

	@abstractmethod
	def set_version_from_arch_versions(self, arch_versions: set[string]) -> string:
		raise NotImplementedError

	@abstractmethod
	def slug(self) -> string:
		raise NotImplementedError

	@abstractmethod
	def kernel_cmdline(self) -> list[string]:
		raise NotImplementedError

	def boot_partition_num(self) -> int:
		log.info("Using default boot partition number: 2")
		return 2

	def boot_dir_prefix(self) -> string:
		log.info("Using default boot directory prefix: (none)")
		return ""

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
		self.oci_images: list[MultiArchImage] = self.get_oci_image_definitions()
		self.oci_images_by_type: dict[str, MultiArchImage] = {}
		for oci_image in self.oci_images:
			self.oci_images_by_type[oci_image.type] = oci_image

		# check if versioned images already exist; if so, do nothing -- no use in rebuilding
		all_up_to_date = True
		for oci_image in self.oci_images:
			skopeo_result = skopeo_inspect_remote_ref(oci_image.full_ref_version)
			log.info(f"skopeo_result: '{skopeo_result}' for '{oci_image.full_ref_version}'")
			if skopeo_result is None:
				all_up_to_date = False

		gha_skopeo = 'yes' if all_up_to_date else 'no'
		set_gha_output("uptodate", gha_skopeo)

		# output GHA outputs with the qcow2 filenames, for GHA caching steps
		for arch in self.arches:
			set_gha_output(f"qcow2-{arch.docker_slug}", arch.qcow2_filename)

		self.template_example()

		# If running on Darwin, log and return. We need Linux to run qemu-nbd.
		if os.uname().sysname != "Linux":
			log.warning("Not on Linux, cannot run qemu-nbd to extract kernel and initrd from qcow2.")
			return

		if os.environ.get("DO_DOWNLOAD_QCOW2", "") == "yes":
			self.download_qcow2()
		if os.environ.get("DO_EXTRACT_KERNEL", "") == "yes":
			self.extract_kernel_initrd()

		for oci_image in self.oci_images:
			log.info("oci_image: %s", oci_image)
			pprint(oci_image)
			if os.environ.get("DO_DOCKER_BUILD", "") == "yes":
				oci_image.build()
			if os.environ.get("DO_DOCKER_PUSH", "") == "yes":
				oci_image.push()
			log.info("--------------------------------------------------------------------------------------------")

		log.info("Done.")

	def template_example(self):
		# use jinja2 to template yaml file

		examples = [
			{
				"name": "kernelboot-ephemeral",
				"template": "vm.ephemeral.kernelboot",
				"description": "Kernel boot, can control kernel cmdline, ephemeral ESP/rootfs disk"
			},
			{
				"name": "efi-ephemeral",
				"template": "vm.ephemeral.efi",
				"description": "EFI boot, distro pre-set kernel cmdline, ephemeral ESP/rootfs disk"
			}
		]

		standard_args = ["consoleblank=0", "loglevel=7", "direct-kernel-boot=yes"]

		for ex in examples:
			example = ex["name"]
			template = jinja2.Template(open(f"info/templates/{ex['template']}.yaml.j2").read())

			for arch in self.arches:
				log.info(pretty_repr(arch))
				output_filename_yaml = f"examples/kubevirt/vms/{self.slug()}-{arch.docker_slug}-{ex['name']}.yaml"

				# render the template
				rendered_template = template.render(
					vm=f"{self.slug()}-{arch.docker_slug}-{example}",
					example=example,
					description=ex['description'],
					slug=self.slug(),
					arch=arch,
					kernel=self.oci_images_by_type["kernel"],
					disk=self.oci_images_by_type["disk"],
					kernel_cmdline=(" ".join(self.kernel_cmdline() + arch.kernel_cmdline() + standard_args)),
				)

				# print the rendered template using rich.syntax
				# from rich.syntax import Syntax
				# singleton_console.print(Syntax(rendered_template, "yaml", line_numbers=True))

				# save the rendered template
				with open(output_filename_yaml, "w") as f:
					f.write(rendered_template)
				log.info(f"Wrote {output_filename_yaml}")
