import logging
import sys

import click

from armbian import Armbian
from debian import Debian
from fedora import Fedora
from rocky import Rocky
from ubuntu import Ubuntu
from utils import setup_logging

log: logging.Logger = setup_logging("cli")


@click.group()
def cli():
	pass


@cli.command(help="Rocky Linux, extracts kernel and initrd from qcow2")
@click.option('--release', envvar="RELEASE", default="8", help='Rocky Linux release; can be 8 or 9, but also 8.8 and 9.3 etc')
@click.option('--variant', envvar="VARIANT", default="GenericCloud-LVM", help='Rocky Linux variant; can be GenericCloud-LVM or GenericCloud')
@click.option('--rocky-mirror', envvar="ROCKY_MIRROR", default="https://dl.rockylinux.org/pub/rocky", help='Rocky Linux mirror')
@click.option(
	'--rocky-vault-mirror', envvar="ROCKY_VAULT_MIRROR", default="https://dl.rockylinux.org/vault/rocky",
	help='Rocky Linux vault mirror, can be https://rocky-linux-europe-west4.production.gcp.mirrors.ctrliq.cloud/pub/rocky')
def rocky(release, variant, rocky_mirror, rocky_vault_mirror):
	try:
		log.info('Rocky')
		r = Rocky(release, variant, rocky_mirror, rocky_vault_mirror)
		r.cli_the_whole_shebang()
	except:
		log.exception("CLI failed")
		sys.exit(1)


@cli.command(help="Fedora Cloud images, extracts kernel and initrd from qcow2")
@click.option('--release', envvar="RELEASE", default="39", help='Fedora release; can be 39 etc')
@click.option('--mirror', envvar="FEDORA_MIRROR", default="https://download.fedoraproject.org/pub/fedora", help='Fedora mirror')
def fedora(release, mirror):
	try:
		log.info('Fedora')
		f = Fedora(release, mirror)
		f.cli_the_whole_shebang()
	except:
		log.exception("CLI failed")
		sys.exit(1)


@cli.command(help="Debian Cloud images, extracts kernel and initrd from qcow2")
@click.option('--release', envvar="RELEASE", default="bookworm", help='Debian release; can be bullseye/bookworm/trixie etc')
# See https://gitlab.com/libosinfo/osinfo-db/-/merge_requests/268
@click.option('--variant', envvar="VARIANT", default="generic", help='Debian Cloud Linux variant; can be genericcloud, generic, or nocloud')
@click.option('--mirror', envvar="DEBIAN_MIRROR", default="https://cloud.debian.org/images/cloud", help='Debian mirror')
def debian(release, variant, mirror):
	try:
		log.info('Debian')
		d = Debian(release, variant, mirror)
		d.cli_the_whole_shebang()
	except:
		log.exception("CLI failed")
		sys.exit(1)


@cli.command(help="Ubuntu Cloud images, extracts kernel and initrd from qcow2")
@click.option('--release', envvar="RELEASE", default="bookworm", help='Ubuntu release; can be bullseye/bookworm/trixie etc')
@click.option('--mirror', envvar="UBUNTU_MIRROR", default="https://cloud-images.ubuntu.com", help='Ubuntu mirror')
def ubuntu(release, mirror):
	try:
		log.info('Ubuntu')
		d = Ubuntu(release, mirror)
		d.cli_the_whole_shebang()
	except:
		log.exception("CLI failed")
		sys.exit(1)


@cli.command(help="Armbian Cloud images, extracts kernel and initrd from qcow2")
@click.option(
	'--release', envvar="RELEASE", default="bookworm",
	help='Armbian release; can be bullseye/bookworm/trixie for Debian but also jammy/mantic/noble etc for Ubuntu variants')
@click.option(
	'--branch', envvar="BRANCH", default="edge", help='Armbian branch, usually current/edge/legacy')
def armbian(release, branch):
	try:
		log.info('Armbian')
		d = Armbian(release, branch)
		d.cli_the_whole_shebang()
	except:
		log.exception("CLI failed")
		sys.exit(1)


if __name__ == '__main__':
	cli()
