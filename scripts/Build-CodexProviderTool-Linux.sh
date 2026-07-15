#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dist_root="$root/dist"
package_name="CodexProviderTool-linux-x64"
package_dir="$dist_root/$package_name"
archive_path="$dist_root/$package_name.tar.gz"
build_root="${CODEX_LINUX_BUILD_ROOT:-$root/build/codex-provider-tool-linux}"
staging_dir="$build_root/release/$package_name"

case "$package_dir" in
  "$root"/*) ;;
  *) echo "Refusing to clean a package path outside the workspace: $package_dir" >&2; exit 1 ;;
esac
case "$staging_dir" in
  "$root"/*|/tmp/*) ;;
  *) echo "Refusing to clean a staging path outside the workspace or /tmp: $staging_dir" >&2; exit 1 ;;
esac

python3 -m PyInstaller --version >/dev/null
mkdir -p "$dist_root" "$build_root"
rm -rf "$staging_dir" "$package_dir"
rm -f "$archive_path"
mkdir -p "$staging_dir" "$package_dir"

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name CodexProviderTool \
  --distpath "$staging_dir" \
  --workpath "$build_root/gui" \
  --specpath "$build_root" \
  "$root/scripts/codex_provider_gui.py"

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --console \
  --name CodexProviderTool-cli \
  --distpath "$staging_dir" \
  --workpath "$build_root/cli" \
  --specpath "$build_root" \
  "$root/scripts/codex_provider_tool.py"

cp "$root/scripts/CODEX-PROVIDER-TOOL-LINUX-README.md" "$staging_dir/README.md"
chmod +x "$staging_dir/CodexProviderTool" "$staging_dir/CodexProviderTool-cli"
(
  cd "$staging_dir"
  sha256sum CodexProviderTool CodexProviderTool-cli > SHA256SUMS.txt
)

cp -a "$staging_dir/." "$package_dir/"
cp "$staging_dir/SHA256SUMS.txt" "$dist_root/SHA256SUMS-linux.txt"
tar -C "$dist_root" -czf "$archive_path" "$package_name"

echo "Linux package directory: $package_dir"
echo "Linux archive:           $archive_path"
