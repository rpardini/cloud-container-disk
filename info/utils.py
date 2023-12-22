# Pay attention, work step by step, use modern (3.10+) Python syntax and features.

import glob
import logging
import os
import string
import subprocess
from urllib.request import urlopen

from bs4 import BeautifulSoup
from rich.console import Console
from rich.logging import RichHandler

log = logging.getLogger("utils")

singleton_console: Console | None = None


def shell(arg_list: list[string]):
	# execute a shell command, passing the shell-escaped arg list; throw and exception if the exit code is not 0
	log.info(f"shell: {arg_list}")
	result = subprocess.run(arg_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if result.returncode != 0:
		raise Exception(
			f"shell command failed: {arg_list} with return code {result.returncode} and stderr {result.stderr}")
	utf8_stdout = result.stdout.decode("utf-8")
	log.debug(f"shell: {arg_list} exitcode: {result.returncode} stdout:\n{utf8_stdout}")
	return utf8_stdout


def shell_passthrough(arg_list: list[string]):
	# execute a shell command, passing the shell-escaped arg list; throw and exception if the exit code is not 0
	log.info(f"shell: {arg_list}")

	# run the process. let it inherit stdin/stdout/stderr
	result = subprocess.run(arg_list)
	if result.returncode != 0:
		raise Exception(
			f"shell command failed: {arg_list} with return code {result.returncode} ")
	log.debug(f"shell: {arg_list} exitcode: {result.returncode}")


# ‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹
#  SPDX-License-Identifier: GPL-2.0
#  Copyright (c) 2023 Ricardo Pardini <ricardo@pardini.net>
#  This file is a part of the Armbian Build Framework https://github.com/armbian/build/
# ‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹‹
class NBDImageMounter:
	nbd_device: string
	image_filename: string

	def __init__(self, device_num, image_filename):
		self.nbd_device = f"/dev/nbd{device_num}"
		self.image_filename = image_filename

	def __enter__(self):
		shell(["udevadm", "settle"])
		log.info(f"Connecting {self.image_filename} to nbd device {self.nbd_device}")
		shell(["qemu-nbd", f"--connect={self.nbd_device}", f"{self.image_filename}"])
		shell(["partprobe", f"{self.nbd_device}"])
		shell(["fdisk", "-l", f"{self.nbd_device}"])
		shell(["lsblk", "-f", f"{self.nbd_device}"])
		return self

	def __exit__(self, *args):
		log.info(f"Disconnecting {self.nbd_device}")
		shell(["qemu-nbd", "--disconnect", f"{self.nbd_device}"])


class DevicePathMounter:
	device_path: string
	partition_num: int
	mountpoint: string

	def __init__(self, device_path, partition_num, mountpoint):
		self.device_path = device_path
		self.partition_num = partition_num
		self.mountpoint = mountpoint

	def __enter__(self):
		log.info(f"Mounting {self.device_path}p{self.partition_num} to {self.mountpoint}")
		shell(["mkdir", "-p", f"{self.mountpoint}"])
		shell([f"mount", f"{self.device_path}p{self.partition_num}", f"{self.mountpoint}"])
		return self

	def __exit__(self, *args):
		log.info(f"Unmounting {self.mountpoint}")
		shell([f"umount", f"{self.mountpoint}"])
		log.info(f"Removing {self.mountpoint}")
		shell(["rmdir", f"{self.mountpoint}"])

	def glob_non_rescue(self, glob_pattern):
		all_globs = glob.glob(glob_pattern, root_dir=f"{self.mountpoint}")
		log.info(f"all_globs: {all_globs}")
		all_globs = [vmlinuz for vmlinuz in all_globs if "-rescue" not in vmlinuz]

		if len(all_globs) != 1:
			if len(all_globs) == 0:
				log.error(f"Found no '{glob_pattern}' files in {self.mountpoint}")
			raise Exception(f"Found {len(all_globs)} '{glob_pattern}' files in {self.mountpoint}: {all_globs}")

		result = all_globs[0]
		log.info(f"glob single result: {result}")

		return result


def get_url_and_parse_html_hrefs(index_url):
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


def global_console() -> Console:
	global singleton_console
	if singleton_console is None:
		raise Exception("setup_logging() must be called before global_console()")
	return singleton_console


# logging with rich
def setup_logging(name: string) -> logging.Logger:
	global singleton_console
	if singleton_console is not None:
		return logging.getLogger(name)

	# GHA hacks
	if os.environ.get("GITHUB_ACTIONS", "") == "":
		singleton_console = Console(width=160)
	else:
		singleton_console = Console(color_system="standard", width=160, highlight=False)

	logging.basicConfig(
		level="DEBUG",
		# format="%(message)s",
		datefmt="[%X]",
		handlers=[RichHandler(rich_tracebacks=True, markup=True, console=singleton_console)]
	)
	return logging.getLogger(name)
