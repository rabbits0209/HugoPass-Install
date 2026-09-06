// Minimal asar extract/pack (no external dependencies).
//
// The Electron asar container format used by Seewo Hugo (and Electron in
// general) is a single flat file laid out as:
//
//   [uint32 magic = 0x04]
//   [uint32 size          = 8 + stringLen]
//   [uint32 payloadSize   = 4 + stringLen]
//   [uint32 stringLen]
//   [JSON header: { "files": <tree> }]
//   [concatenated file contents]
//
// Each file entry in the header tree is  { size: <number>, offset: "<string>" }.
// A directory entry is                       { files: { ... } }.
// A file's bytes live at  (16 + stringLen + offset).
//
// This layout was verified against a real app.asar produced by
// @cvte/electron-app-builder; `extract` + `pack` round-trips losslessly.

const fs = require("fs");
const path = require("path");

/**
 * Extract an asar archive into `destDir` (created if needed).
 * Empty directories are preserved.
 *
 * @param {string} asarPath
 * @param {string} destDir
 * @returns {number} number of files written
 */
function extract(asarPath, destDir) {
  const fd = fs.openSync(asarPath, "r");

  const head = Buffer.alloc(8);
  fs.readSync(fd, head, 0, 8, 0);
  const size = head.readUInt32LE(4); // bytes 4..7

  const headerBuf = Buffer.alloc(size);
  fs.readSync(fd, headerBuf, 0, size, 8); // bytes 8..8+size

  const stringLen = headerBuf.readUInt32LE(4); // bytes 12..15 of the file
  const json = headerBuf.toString("utf8", 8, 8 + stringLen);
  const header = JSON.parse(json);

  const dataStart = 16 + stringLen;

  let count = 0;

  function walk(node, relDir) {
    for (const [name, entry] of Object.entries(node)) {
      const outPath = path.join(destDir, relDir, name);
      if (entry.files) {
        fs.mkdirSync(outPath, { recursive: true });
        walk(entry.files, path.join(relDir, name));
      } else {
        fs.mkdirSync(path.dirname(outPath), { recursive: true });
        const offset = parseInt(entry.offset, 10);
        const buf = Buffer.alloc(entry.size);
        fs.readSync(fd, buf, 0, entry.size, dataStart + offset);
        fs.writeFileSync(outPath, buf);
        count++;
      }
    }
  }

  walk(header.files, "");
  fs.closeSync(fd);
  return count;
}

/**
 * Pack a directory tree into an asar archive buffer.
 *
 * @param {string} srcDir
 * @returns {Buffer}
 */
function pack(srcDir) {
  const fileBuffers = [];
  let offset = 0;

  function buildNode(relDir) {
    const fullPath = relDir ? path.join(srcDir, relDir) : srcDir;
    const entries = fs
      .readdirSync(fullPath, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name));

    const node = { files: {} };
    for (const ent of entries) {
      const childRel = relDir ? path.join(relDir, ent.name) : ent.name;
      if (ent.isDirectory()) {
        node.files[ent.name] = buildNode(childRel);
      } else if (ent.isFile()) {
        const buf = fs.readFileSync(path.join(fullPath, ent.name));
        node.files[ent.name] = { size: buf.length, offset: String(offset) };
        fileBuffers.push(buf);
        offset += buf.length;
      }
      // symlinks and other special files are intentionally skipped.
    }
    return node;
  }

  const header = { files: buildNode("").files };

  const json = JSON.stringify(header);
  const stringLen = Buffer.byteLength(json, "utf8");
  const size = 8 + stringLen;
  const payloadSize = 4 + stringLen;
  const dataStart = 16 + stringLen;

  const out = Buffer.alloc(dataStart + offset);
  out.writeUInt32LE(4, 0);
  out.writeUInt32LE(size, 4);
  out.writeUInt32LE(payloadSize, 8);
  out.writeUInt32LE(stringLen, 12);
  out.write(json, 16, "utf8");

  let pos = dataStart;
  for (const buf of fileBuffers) {
    buf.copy(out, pos);
    pos += buf.length;
  }

  return out;
}

module.exports = { extract, pack };
