#!/bin/bash

CORES=$(nproc)
TAR=0
FORCE_REMOVE=0
ARCH="x86_64"
KERNEL_CONFIG="allmodconfig"
VERSION=
KERNEL_DIR=
SKIP_MAKE_COMMAND="none"
DISABLES=

usage()
{
    echo "Create Build bases for Klever"
    echo "Usage: $0 [options]"
    echo "       --version <name> - Linux kernel version (specify to download corresponding Linux kernel archive)"
    echo "       --kernel-dir <path> - directory with Linux kernel (specify to use existing kernel directory);"
    echo "             either --version or --kernel-dir argument is a mandatory"
    echo "       --cif <path> - path to CIF executable (mandatory argument)"
    echo "       --workdir <path> - working directory, where the build base will be created (mandatory argument)"
    echo "       --tar - create tar archive containing the build base"
    echo "       --force - clear build base directory"
    echo "       --arch <name> - architecture (by default, $ARCH)"
    echo "       --jobs <number> - number of parallel jobs (by default, $CORES)"
    echo "       --kernel-config <name> - make command (by default, $KERNEL_CONFIG). Use '$SKIP_MAKE_COMMAND' to skip it"
    echo "       --disable <list of options> - disable kernel options"
    exit 1
}

while [[ "$1" != "" ]]; do
    case $1 in
        --version )       shift; VERSION="$1" ;;
        --kernel-dir )    shift; KERNEL_DIR="$1" ;;
        --cif )           shift; CIF="$1" ;;
        --workdir )       shift; WORK_DIR="$1" ;;
        --arch )          shift; ARCH="$1" ;;
        --jobs )          shift; CORES="$1" ;;
        --tar )           TAR=1 ;;
        --force )         FORCE_REMOVE=1 ;;
        --kernel-config ) shift; KERNEL_CONFIG="$1" ;;
        --disable)
            shift
            [[ -n "${1:-}" ]] || { echo "ERROR: --disable requires options"; exit 2; }
            DISABLES+=("$1")
            ;;
        -h | --help )     usage ;;
        * )               usage ;;
    esac
    shift
done

if [ -n "$VERSION" ] && [ -n "$KERNEL_DIR" ]; then
    echo "Sanity check failed: both --version and --kernel-dir were specified"
    usage
fi

if [ -z "$VERSION" ] && [ -z "$KERNEL_DIR" ]; then
    echo "Sanity check failed: neither --version or --kernel-dir were specified"
    usage
fi

if [ -n "$KERNEL_DIR" ] && [ ! -d "$KERNEL_DIR" ]; then
    echo "Directory with kernel $KERNEL_DIR does not exist"
    usage
fi

if [ ! "$WORK_DIR" ]; then
    echo "Working directory was not specified"
    usage
fi

if [ ! -e "$CIF" ]; then
    echo "CIF executable '$CIF' does not exist"
    usage
fi

if [ ! "$ARCH" == "x86_64" ]; then
    echo "Architecture $ARCH is not supported"
    exit 1
fi

if ! command -v clade &> /dev/null ; then
    echo "Clade was not installed"
    exit 1
fi

clade_version=$(clade -v)

if [ ! "$clade_version" == "Clade 3.6" ]; then
    echo "Only clade version 3.6 is supported"
    exit 1
fi

if [ ! -e "$WORK_DIR" ]; then
    mkdir -p "$WORK_DIR" || { echo "Cannot create working directory $WORK_DIR" ; exit 1; }
fi

CIF=$(realpath "$CIF")
WORK_DIR=$(realpath "$WORK_DIR")

if [ -n "$VERSION" ]; then
  echo "Create the build base for Linux kernel version $VERSION"
  kernel_id=${VERSION:0:1}
  KERNEL_ARCHIVE=linux-$VERSION.tar.xz
  kernel_dir="linux-$VERSION"
  build_base_rel_dir="build-base-linux-$VERSION-$ARCH-$KERNEL_CONFIG"
else
  echo "Create the build base for Linux kernel $KERNEL_DIR"
  kernel_dir=$(realpath "$KERNEL_DIR")
  base_name=$(basename "$KERNEL_DIR")
  build_base_rel_dir="build-base-$base_name-$ARCH-$KERNEL_CONFIG"
fi

build_base_dir="$WORK_DIR/$build_base_rel_dir"

echo "Using work dir $WORK_DIR"
echo "Architecture: $ARCH"
echo "Path to CIF executable: $CIF"

if [ -n "$VERSION" ]; then
  cd "$WORK_DIR" || { echo "Cannot change dir to $WORK_DIR" ; exit 1; }
  if [ ! -e "$KERNEL_ARCHIVE" ]; then
    echo "Download Linux kernel archive"
    wget "https://cdn.kernel.org/pub/linux/kernel/v$kernel_id.x/$KERNEL_ARCHIVE" || { echo "Cannot download Linux kernel archive $KERNEL_ARCHIVE" ; exit 1; }
  fi
  if [ -d "$kernel_dir" ]; then
    rm -rf "$kernel_dir"
  fi
  tar -xf "$KERNEL_ARCHIVE"
fi
cd "$kernel_dir" || { echo "Cannot change dir to $kernel_dir" ; exit 1; }

if [ -n "$KERNEL_DIR" ]; then
  echo "Clean kernel directory"
  make -j "$CORES" clean
fi

if [ ! "$KERNEL_CONFIG" == "$SKIP_MAKE_COMMAND" ]; then
  echo "Generate kernel config: make $KERNEL_CONFIG"
  make "$KERNEL_CONFIG" || { echo "Cannot execute make $KERNEL_CONFIG" ; exit 1; }
  if ((${#DISABLES[@]})); then
    args=()
    for sym in "${DISABLES[@]}"; do
        args+=(--disable "$sym")
    done
    scripts/config "${args[@]}"
    make oldconfig
  fi
fi

if [ "$FORCE_REMOVE" -ne 0 ]; then
  rm -rf "$build_base_dir"
fi

time clade -w "$build_base_dir" -p klever_linux_kernel --cif "$CIF" -e SrcGraph make -j "$CORES" modules || { echo 'Cannot build SrcGraph' ; exit 1; }
time clade -w "$build_base_dir" -p klever_linux_kernel --cif "$CIF" -e Callgraph || { echo 'Cannot build Callgraph' ; exit 1; }
time clade -w "$build_base_dir" -p klever_linux_kernel --cif "$CIF" || { echo 'Cannot build CrossRef' ; exit 1; }

echo "The build base was successfully prepared in $build_base_dir"

if [ "$TAR" -ne 0 ]; then
  cd "$WORK_DIR" || { echo "Cannot change dir to $WORK_DIR" ; exit 1; }
  tar cfJ "$build_base_rel_dir.tar.xz" "$build_base_rel_dir"
  echo "The build base was successfully exported in $build_base_rel_dir.tar.xz"
fi
