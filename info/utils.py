# Pay attention, work step by step, use modern (3.10+) Python syntax and features.

import glob
import string
import subprocess


def shell(arg_list: list[string]):
	# execute a shell command, passing the shell-escaped arg list; throw and exception if the exit code is not 0
	print(f"shell: {arg_list}")
	result = subprocess.run(arg_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if result.returncode != 0:
		raise Exception(
			f"shell command failed: {arg_list} with return code {result.returncode} and stderr {result.stderr}")
	utf8_stdout = result.stdout.decode("utf-8")
	print(f"shell: {arg_list} exitcode: {result.returncode} stdout:\n{utf8_stdout}")
	return utf8_stdout


def shell_passthrough(arg_list: list[string]):
	# execute a shell command, passing the shell-escaped arg list; throw and exception if the exit code is not 0
	print(f"shell: {arg_list}")

	# run the process. let it inherit stdin/stdout/stderr
	result = subprocess.run(arg_list)
	if result.returncode != 0:
		raise Exception(
			f"shell command failed: {arg_list} with return code {result.returncode} ")
	print(f"shell: {arg_list} exitcode: {result.returncode}")


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
		print(f"Connecting {self.image_filename} to nbd device {self.nbd_device}")
		shell(["qemu-nbd", f"--connect={self.nbd_device}", f"{self.image_filename}"])
		shell(["partprobe", f"{self.nbd_device}"])
		shell(["fdisk", "-l", f"{self.nbd_device}"])
		shell(["lsblk", "-f", f"{self.nbd_device}"])
		return self

	def __exit__(self, *args):
		print(f"Disconnecting {self.nbd_device}")
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
		print(f"Mounting {self.device_path}p{self.partition_num} to {self.mountpoint}")
		shell(["mkdir", "-p", f"{self.mountpoint}"])
		shell([f"mount", f"{self.device_path}p{self.partition_num}", f"{self.mountpoint}"])
		return self

	def __exit__(self, *args):
		print(f"Unmounting {self.mountpoint}")
		print(f"Unmounting {self.mountpoint}")
		shell([f"umount", f"{self.mountpoint}"])

	def glob_non_rescue(self, glob_pattern):
		all_globs = glob.glob(glob_pattern, root_dir=f"{self.mountpoint}")
		print(f"all_globs: {all_globs}")
		all_globs = [vmlinuz for vmlinuz in all_globs if "-rescue" not in vmlinuz]

		if len(all_globs) != 1:
			raise Exception(f"Found {len(all_globs)} '{glob_pattern}' files in {self.mountpoint}: {all_globs}")

		result = all_globs[0]
		print(f"glob single result: {result}")

		return result
