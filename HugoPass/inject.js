#!/usr/bin/env node
// HugoPass injector: unpack app.asar -> patch vendor.js -> repack.
//
// Usage:
//   node inject.js [path-to-app.asar]
//   node inject.js [path-to-app.asar] --install   (replace in place, keep .orig backup)
//
// If no path is given, it falls back to config.json's `asarPath`, then to the
// default Seewo Hugo install location.

const fs = require("fs");
const path = require("path");

const { extract, pack } = require("./lib/asar");
const { patchVendorJs } = require("./lib/patch");
const { updateVerifyJson, crc32Of, crc32HexLE } = require("./lib/verify");

const PROJECT_ROOT = __dirname;
const BUILD_DIR = path.join(PROJECT_ROOT, "build");
const CONFIG_PATH = path.join(PROJECT_ROOT, "config.json");

const SEEWO_SERVICE_ROOT = "C:\\Program Files (x86)\\Seewo\\SeewoService";

// Seewo installs each version under SeewoService_<version>\SeewoServiceAssistant.
// The app.asar lives at SeewoServiceAssistant\resources\app.asar on newer
// builds, and directly at SeewoServiceAssistant\app.asar on older ones.
// Pick the newest version that has an app.asar in either location.
function findInstalledAsar() {
  if (!fs.existsSync(SEEWO_SERVICE_ROOT)) return null;
  const candidates = [];

  const dirs = fs
    .readdirSync(SEEWO_SERVICE_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name.startsWith("SeewoService_"));

  for (const d of dirs) {
    const base = path.join(SEEWO_SERVICE_ROOT, d.name, "SeewoServiceAssistant");
    for (const rel of ["app.asar", path.join("resources", "app.asar")]) {
      const p = path.join(base, rel);
      if (fs.existsSync(p)) candidates.push(p);
    }
  }

  if (candidates.length === 0) return null;

  candidates.sort((a, b) => {
    const va = a.split("SeewoService_")[1]?.split("\\")[0] || "";
    const vb = b.split("SeewoService_")[1]?.split("\\")[0] || "";
    return vb.localeCompare(va, undefined, { numeric: true });
  });
  return candidates[0];
}

function loadConfig() {
  if (!fs.existsSync(CONFIG_PATH)) {
    throw new Error(`config.json not found at ${CONFIG_PATH}`);
  }
  return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
}

function resolveAsarPath(args) {
  const positional = args.filter((a) => a !== "--install");
  if (positional.length > 0) return positional[0];

  const config = loadConfig();
  if (config.asarPath) return config.asarPath;

  return findInstalledAsar();
}

function main() {
  const args = process.argv.slice(2);
  const install = args.includes("--install");
  const asarPath = resolveAsarPath(args);

  const config = loadConfig();

  if (!config.enabled) {
    console.log("[HugoPass] config.enabled is false — nothing to do.");
    return;
  }

  if (config.mode !== "bypass" && config.mode !== "customPassword") {
    throw new Error(
      `config.mode must be "bypass" or "customPassword", got "${config.mode}".`
    );
  }

  if (!asarPath || !fs.existsSync(asarPath)) {
    throw new Error(
      `app.asar not found${asarPath ? ` at "${asarPath}"` : ""}. Pass the ` +
        `correct path as an argument or set "asarPath" in config.json.`
    );
  }

  const workDir = path.join(BUILD_DIR, "app-extracted");
  fs.rmSync(workDir, { recursive: true, force: true });
  fs.mkdirSync(workDir, { recursive: true });

  console.log(`[HugoPass] Extracting ${asarPath} ...`);
  const fileCount = extract(asarPath, workDir);
  console.log(`[HugoPass] Extracted ${fileCount} files.`);

  const vendorPath = path.join(workDir, "public", "vendor.js");
  if (!fs.existsSync(vendorPath)) {
    throw new Error(`public/vendor.js not found in the extracted archive.`);
  }

  const vendorJs = fs.readFileSync(vendorPath, "utf8");
  console.log(`[HugoPass] Patching public/vendor.js (mode: ${config.mode}) ...`);
  const { code, mode } = patchVendorJs(vendorJs, config);
  fs.writeFileSync(vendorPath, code, "utf8");
  console.log(`[HugoPass] Patched successfully.`);

  const outAsar = path.join(BUILD_DIR, "app.asar");
  fs.mkdirSync(BUILD_DIR, { recursive: true });
  console.log(`[HugoPass] Repacking to ${outAsar} ...`);
  const packed = pack(workDir);
  fs.writeFileSync(outAsar, packed);

  const newCrc = crc32Of(packed);
  console.log(`[HugoPass] New app.asar CRC32: ${newCrc} (${crc32HexLE(newCrc)})`);

  console.log(`\n[HugoPass] Done. Patched archive written to:`);
  console.log(`  ${outAsar}`);

  if (install) {
    const backup = asarPath + ".orig";
    if (!fs.existsSync(backup)) {
      fs.copyFileSync(asarPath, backup);
      console.log(`\n[HugoPass] Original backed up to ${backup}`);
    }
    fs.copyFileSync(outAsar, asarPath);
    console.log(`[HugoPass] Installed into ${asarPath}`);

    updateVerifyJson(asarPath, newCrc);
  } else {
    console.log(`\n[HugoPass] To install, either:`);
    console.log(`  1. Run with --install to replace the original (backup kept), or`);
    console.log(`  2. Manually copy build/app.asar over the real app.asar.`);
    console.log(`\n  Real location: ${asarPath}`);
    console.log(`\n  NOTE: after replacing app.asar, its CRC32 must also be refreshed in`);
    console.log(`  Verify.json or the launcher may refuse to start. --install does this`);
    console.log(`  automatically.`);
  }
}

try {
  main();
} catch (err) {
  console.error(`\n[HugoPass / Error] ${err.message}`);
  process.exit(1);
}
