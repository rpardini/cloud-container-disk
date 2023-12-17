#!/usr/bin/env bash
#
# SPDX-License-Identifier: GPL-2.0
# Copyright (c) 2023 Ricardo Pardini <ricardo@pardini.net>
#

set -e

declare DISK_OCI_REF="${DISK_OCI_REF:-"ghcr.io/rpardini/armbian-cloud-container-disk"}"
declare KERNEL_OCI_REF="${KERNEL_OCI_REF:-"ghcr.io/rpardini/armbian-cloud-kernel-kv"}"

function output_list_of_candidates() {
	jq -r ".assets[].browser_download_url" latest.json | grep "${ARCH_TOKEN}_" | grep "_${RELEASE_TOKEN}_" | grep "_${KERNEL_TOKEN}_"
}

# First arg is the target multiarch ref, the second is a nameref to a dict of arch_name -> oci_ref
function multiarch_manifest_create_and_push() {
	echo "Will do multiarch manifest for $1"

	# remove the manifest so it starts up empty
	echo "-- Deleting manifest $1..."
	docker manifest rm "$1" || true
	
	#echo "-- Showing manifest $1 after deletion..."
	#docker manifest inspect "$1" || true

	declare -a cmd=(docker manifest create "$1")

	# nameref
	declare -n arches_ref="$2"

	# loop over the values of the arches_def dict
	for arch in "${!arches_ref[@]}"; do
		echo "Will add arch '$arch' manifest '${arches_ref[$arch]}'"
		cmd+=("${arches_ref[$arch]}") # --amend
	done

	echo "Creating manifest $1..."
	"${cmd[@]}"

	echo "-- Showing manifest $1 after initial creation..."
	docker manifest inspect --verbose "$1" || true

	# loop over the values of the arches_def dict
	for arch in "${!arches_ref[@]}"; do
		echo "Will annotate arch '$arch' manifest '${arches_ref[$arch]}'"
		docker manifest annotate --arch "$arch" "$1" "${arches_ref[$arch]}"

		echo "-- Showing manifest $1 after annnotating arch $arch..."
		docker manifest inspect "$1" || true
	done

	echo "-- Showing manifest $1 before push..."
	docker manifest inspect --verbose "$1" || true

	echo "Pushing manifest $1..."
	docker manifest push "$1"

	echo "-- Showing manifest $1 after push..."
	docker manifest inspect --verbose "$1" || true

}

if [[ ! -f latest.json ]]; then
	curl "https://api.github.com/repos/${SOURCE_OWNER_REPO_RELEASES:-"rpardini/armbian-release"}/releases/latest" > latest.json
fi

# parse the release name
TAG_NAME=$(jq -r '.tag_name' latest.json)

declare -a ARCH_TOKENS=("Uefi-x86" "Uefi-arm64") #
declare -A ARCH_TOKENS_MAP=(["Uefi-x86"]="amd64" ["Uefi-arm64"]="arm64")
declare -a RELEASE_TOKENS=("${RELEASE:-"bookworm"}")
declare -a KERNEL_TOKENS=("${BRANCH:-"edge"}")

for RELEASE_TOKEN in "${RELEASE_TOKENS[@]}"; do
	echo "Doing for RELEASE_TOKEN:" "${RELEASE_TOKEN}"
	for KERNEL_TOKEN in "${KERNEL_TOKENS[@]}"; do
		echo "Doing for KERNEL_TOKEN:" "${KERNEL_TOKEN}"

		# dict of arch->oci_ref for later multiarch manifest
		declare -A KERNEL_ARCHES_VERSION=() KERNEL_ARCHES_LATEST=()
		declare -A DISK_ARCHES_VERSION=() DISK_ARCHES_LATEST=()

		for ARCH_TOKEN in "${ARCH_TOKENS[@]}"; do
			echo "Doing for ARCH_TOKEN:" "${ARCH_TOKEN}"
			# Lookup in the map
			declare DOCKER_ARCH="${ARCH_TOKENS_MAP[${ARCH_TOKEN}]}"
			echo "DOCKER_ARCH:" "${DOCKER_ARCH}"

			declare -a QCOW2_URLS=() KERNEL_URLS=() INITRD_URLS=()

			# https://github.com/rpardini/armbian-release/releases/download/23.12.10-rpardini-756/Armbian-unofficial_23.12.10-rpardini-756_Uefi-x86_bookworm_edge_6.6.5-metadata-cloud.img.qcow2.xz
			# https://github.com/rpardini/armbian-release/releases/download/23.12.10-rpardini-756/Armbian-unofficial_23.12.10-rpardini-756_Uefi-x86_bookworm_edge_6.6.5-metadata-cloud.kernel.xz
			# https://github.com/rpardini/armbian-release/releases/download/23.12.10-rpardini-756/Armbian-unofficial_23.12.10-rpardini-756_Uefi-x86_bookworm_edge_6.6.5-metadata-cloud.initrd.xz
			mapfile -t QCOW2_URLS < <(output_list_of_candidates | grep "metadata-cloud\.img\.qcow2\.xz")
			mapfile -t KERNEL_URLS < <(output_list_of_candidates | grep "metadata-cloud\.kernel\.xz")
			mapfile -t INITRD_URLS < <(output_list_of_candidates | grep "metadata-cloud\.initrd\.xz")

			echo "Got qcow2s:" "${QCOW2_URLS[@]}"
			echo "Got kernels:" "${KERNEL_URLS[@]}"
			echo "Got initrds:" "${INITRD_URLS[@]}"

			# Make sure we only have one of each
			[[ "${#QCOW2_URLS[@]}" -ne 1 ]] && echo "ERROR: Got more than one qcow2!" && exit 3
			[[ "${#KERNEL_URLS[@]}" -ne 1 ]] && echo "ERROR: Got more than one kernel!" && exit 4
			[[ "${#INITRD_URLS[@]}" -ne 1 ]] && echo "ERROR: Got more than one initrd!" && exit 5

			declare -A INFO_MAP=()

			declare -A URL_MAP=(["kernel"]="${KERNEL_URLS[0]}" ["initrd"]="${INITRD_URLS[0]}" ["qcow2"]="${QCOW2_URLS[0]}")
			# loop over the map
			for URL_TYPE in "${!URL_MAP[@]}"; do
				echo "URL_TYPE:" "${URL_TYPE}"
				declare URL="${URL_MAP[${URL_TYPE}]}"
				echo "URL:" "${URL}"
				declare filename_in_url="${URL##*/}"
				echo "filename_in_url:" "${filename_in_url}"
				declare filename_sans_xz_suffix="${filename_in_url%.xz}"
				echo "filename_sans_xz_suffix:" "${filename_sans_xz_suffix}"
				# add to the INFO_MAP
				INFO_MAP["${URL_TYPE}_url"]="${URL}"
				INFO_MAP["${URL_TYPE}_filename_xz"]="${filename_in_url}"
				INFO_MAP["${URL_TYPE}_filename"]="${filename_sans_xz_suffix}"
			done

			# Download & uncompress the files
			for URL_TYPE in "${!URL_MAP[@]}"; do
				echo "Will download & decompress URL_TYPE:" "${URL_TYPE}"
				declare url="${INFO_MAP[${URL_TYPE}_url]}"
				echo "url:" "${url}"
				declare filename_xz="${INFO_MAP[${URL_TYPE}_filename_xz]}"
				echo "filename_xz:" "${filename_xz}"
				declare filename="${INFO_MAP[${URL_TYPE}_filename]}"
				echo "filename:" "${filename}"

				# If we already have the filename, we're done
				if [[ -f "${filename}" ]]; then
					echo "Already have ${filename}, skipping download."
				else
					# If we already have the download, just decompress
					if [[ ! -f "${filename_xz}" ]]; then
						echo "Downloading ${url} to ${filename_xz}.tmp ..."
						curl -L "${url}" -o "${filename_xz}.tmp"
						mv -v "${filename_xz}.tmp" "${filename_xz}"
					fi
					echo "Uncompressing ${filename_xz} to ${filename} ..."
					pixz -d "${filename_xz}"
				fi
			done

			# Calculate the OCI coordinates for the Container Disk & Kernel images
			declare OCI_TAG_VERSION="${RELEASE_TOKEN}-${KERNEL_TOKEN}-${DOCKER_ARCH}-${TAG_NAME}"
			declare OCI_TAG_LATEST="${RELEASE_TOKEN}-${KERNEL_TOKEN}-${DOCKER_ARCH}-latest"

			declare DISK_OCI_REF_VERSION="${DISK_OCI_REF}:${OCI_TAG_VERSION}"
			declare DISK_OCI_REF_LATEST="${DISK_OCI_REF}:${OCI_TAG_LATEST}"

			declare KERNEL_OCI_REF_VERSION="${KERNEL_OCI_REF}:${OCI_TAG_VERSION}"
			declare KERNEL_OCI_REF_LATEST="${KERNEL_OCI_REF}:${OCI_TAG_LATEST}"

			echo "DISK_OCI_REF_VERSION:" "${DISK_OCI_REF_VERSION}"
			echo "DISK_OCI_REF_LATEST:" "${DISK_OCI_REF_LATEST}"
			echo "KERNEL_OCI_REF_VERSION:" "${KERNEL_OCI_REF_VERSION}"
			echo "KERNEL_OCI_REF_LATEST:" "${KERNEL_OCI_REF_LATEST}"

			# Build the KERNEL image (which has kernel & initrd) for KubeVirt's kernelBoot.container
			cat <<- DOCKERFILE_KERNEL > Dockerfile.kernel
				FROM scratch
				ADD --chown=107:107 ${INFO_MAP["kernel_filename"]} /boot/vmlinuz
				ADD --chown=107:107 ${INFO_MAP["initrd_filename"]} /boot/initrd
			DOCKERFILE_KERNEL

			cat <<- DOCKERIGNORE_KERNEL > .dockerignore
				*
				!${INFO_MAP["kernel_filename"]}
				!${INFO_MAP["initrd_filename"]}
			DOCKERIGNORE_KERNEL

			# Build the KERNEL image
			docker build -t "${KERNEL_OCI_REF_VERSION}" -f Dockerfile.kernel .
			rm -f Dockerfile.kernel .dockerignore
			docker tag "${KERNEL_OCI_REF_VERSION}" "${KERNEL_OCI_REF_LATEST}"

			# Push the image to the registry
			docker push "${KERNEL_OCI_REF_VERSION}"
			docker push "${KERNEL_OCI_REF_LATEST}"

			# Store in dictionary (for later multiarch manifest)
			KERNEL_ARCHES_VERSION["${DOCKER_ARCH}"]="${KERNEL_OCI_REF_VERSION}"
			KERNEL_ARCHES_LATEST["${DOCKER_ARCH}"]="${KERNEL_OCI_REF_LATEST}"

			# Create Docker images as KubeVirt likes them (ContainerDisk)
			cat <<- DOCKERFILE_DISK > Dockerfile.disk
				FROM scratch
				ADD --chown=107:107 ${INFO_MAP["qcow2_filename"]} /disk/${INFO_MAP["qcow2_filename"]}
			DOCKERFILE_DISK

			cat <<- DOCKERIGNORE_DISK > .dockerignore
				*
				!${INFO_MAP["qcow2_filename"]}
			DOCKERIGNORE_DISK

			# Build the DISK image
			docker build -t "${DISK_OCI_REF_VERSION}" -f Dockerfile.disk .
			rm -f Dockerfile.disk .dockerignore
			docker tag "${DISK_OCI_REF_VERSION}" "${DISK_OCI_REF_LATEST}"

			# Push the image to the registry
			docker push "${DISK_OCI_REF_VERSION}"
			docker push "${DISK_OCI_REF_LATEST}"

			# Store in dictionary (for later multiarch manifest)
			DISK_ARCHES_VERSION["${DOCKER_ARCH}"]="${DISK_OCI_REF_VERSION}"
			DISK_ARCHES_LATEST["${DOCKER_ARCH}"]="${DISK_OCI_REF_LATEST}"

			echo "-----------------------------------------------------------------------------------------------------"

		done

		# Now do the multiarch version, combining the two+ arches
		# Needs to be done for both the kernel & the disk
		# Calculate the OCI coordinates for the Container Disk & Kernel images, multi-arch version
		declare OCI_TAG_VERSION="${RELEASE_TOKEN}-${KERNEL_TOKEN}-${TAG_NAME}"
		declare OCI_TAG_LATEST="${RELEASE_TOKEN}-${KERNEL_TOKEN}-latest"

		declare DISK_OCI_REF_VERSION="${DISK_OCI_REF}:${OCI_TAG_VERSION}"
		declare DISK_OCI_REF_LATEST="${DISK_OCI_REF}:${OCI_TAG_LATEST}"

		declare KERNEL_OCI_REF_VERSION="${KERNEL_OCI_REF}:${OCI_TAG_VERSION}"
		declare KERNEL_OCI_REF_LATEST="${KERNEL_OCI_REF}:${OCI_TAG_LATEST}"

		echo "Multiarch version kernel:"
		echo "KERNEL_OCI_REF_VERSION:" "${KERNEL_OCI_REF_VERSION}"
		multiarch_manifest_create_and_push "${KERNEL_OCI_REF_VERSION}" KERNEL_ARCHES_VERSION
		echo "KERNEL_OCI_REF_LATEST:" "${KERNEL_OCI_REF_LATEST}"
		multiarch_manifest_create_and_push "${KERNEL_OCI_REF_LATEST}" KERNEL_ARCHES_LATEST

		echo "Multiarch version disk:"
		echo "DISK_OCI_REF_VERSION:" "${DISK_OCI_REF_VERSION}"
		multiarch_manifest_create_and_push "${DISK_OCI_REF_VERSION}" DISK_ARCHES_VERSION
		echo "DISK_OCI_REF_LATEST:" "${DISK_OCI_REF_LATEST}"
		multiarch_manifest_create_and_push "${DISK_OCI_REF_LATEST}" DISK_ARCHES_LATEST

	done

done
