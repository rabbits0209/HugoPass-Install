// Seewo launcher integrity manifest (Verify.json) handling.
//
// The launcher (SeewoService) stores CRC32 checksums for a set of shipped files
// in SeewoServiceAssistant\Verify.json, including `resources/app.asar`. After we
// replace app.asar we must refresh that entry, or the launcher may refuse to
// start or restore the original file.

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

// Verify.json convention (confirmed against a real file):
//   file_crc32     = unsigned CRC32 (IEEE 802.3 / zlib), decimal
//   file_crc32_hex = the CRC32 bytes written little-endian, as 8 hex chars
function crc32Of(buf) {
  return zlib.crc32(buf) >>> 0;
}

function crc32HexLE(crc) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(crc, 0);
  return b.toString("hex");
}

/**
 * Locate Verify.json for a given app.asar path.
 *   New layout: ...\SeewoServiceAssistant\resources\app.asar -> Verify.json at
 *               ...\SeewoServiceAssistant\Verify.json
 *   Old layout: ...\SeewoServiceAssistant\app.asar        -> Verify.json beside it
 * @param {string} asarPath
 * @returns {string|null}
 */
function locateVerifyJson(asarPath) {
  const candidates = [
    path.join(path.dirname(path.dirname(asarPath)), "Verify.json"),
    path.join(path.dirname(asarPath), "Verify.json"),
  ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

/**
 * Update the app.asar entry in Verify.json to `crc` (keeps a .orig backup).
 * @param {string} asarPath - the app.asar path being deployed
 * @param {number} crc - unsigned CRC32 of the new app.asar
 * @returns {boolean} whether Verify.json was updated
 */
function updateVerifyJson(asarPath, crc) {
  const verifyPath = locateVerifyJson(asarPath);
  if (!verifyPath) {
    console.warn("[HugoPass] Verify.json not found — integrity manifest left unchanged.");
    return false;
  }

  const asarRel = path
    .relative(path.dirname(verifyPath), asarPath)
    .split(path.sep)
    .join("/");

  const list = JSON.parse(fs.readFileSync(verifyPath, "utf8"));

  const verifyBackup = verifyPath + ".orig";
  if (!fs.existsSync(verifyBackup)) {
    fs.copyFileSync(verifyPath, verifyBackup);
    console.log(`[HugoPass] Verify.json backed up to ${verifyBackup}`);
  }

  const entry = list.find((e) => e.file_path === asarRel);
  if (!entry) {
    list.push({
      file_crc32: crc,
      file_crc32_hex: crc32HexLE(crc),
      file_path: asarRel,
    });
    console.log(`[HugoPass] Verify.json: added entry for ${asarRel}`);
  } else {
    entry.file_crc32 = crc;
    entry.file_crc32_hex = crc32HexLE(crc);
    console.log(`[HugoPass] Verify.json: updated ${asarRel} -> ${crc32HexLE(crc)}`);
  }

  // Match the original file's 3-space indentation.
  fs.writeFileSync(verifyPath, JSON.stringify(list, null, 3) + "\n", "utf8");
  return true;
}

module.exports = { crc32Of, crc32HexLE, locateVerifyJson, updateVerifyJson };
