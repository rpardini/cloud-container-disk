import logging

import click

from rocky import Rocky
from utils import setup_logging

log: logging.Logger = setup_logging("rocky")


@click.group()
def cli():
	pass


@cli.command(help="Rocky Linux, extracts kernel and initrd from qcow2")
@click.option('--release', envvar="RELEASE", default="8",
			  help='Rocky Linux release; can be 8 or 9, but also 8.8 and 9.3 etc')
@click.option('--variant', envvar="VARIANT", default="GenericCloud-LVM",
			  help='Rocky Linux variant; can be GenericCloud-LVM or GenericCloud')
@click.option('--rocky-mirror', envvar="ROCKY_MIRROR", default="https://dl.rockylinux.org/pub/rocky",
			  help='Rocky Linux mirror')
@click.option('--rocky-vault-mirror', envvar="ROCKY_VAULT_MIRROR", default="https://dl.rockylinux.org/vault/rocky",
			  help='Rocky Linux vault mirror, can be https://rocky-linux-europe-west4.production.gcp.mirrors.ctrliq.cloud/pub/rocky')
def rocky(release, variant, rocky_mirror, rocky_vault_mirror):
	log.info('Rocky')
	r = Rocky(release, variant, rocky_mirror, rocky_vault_mirror)
	r.cli_the_whole_shebang()


@cli.command()
def fedora():
	click.echo('Fedora')


if __name__ == '__main__':
	cli()
