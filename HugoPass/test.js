// Self-contained tests for the HugoPass core libraries (no external deps).
// Run with:  node test.js

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { extract, pack } = require("./lib/asar");
const { patchVendorJs, TARGET, ORIGINAL_FAIL } = require("./lib/patch");
const { crc32Of, crc32HexLE, updateVerifyJson } = require("./lib/verify");

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL  ${name}\n      ${e.message}`);
  }
}

console.log("lib/patch");

const fakeVendor = `
  var H="passwordSuccess",G="passwordFail",W="requestLimit",J="requestError",q="ADMIN_LOCK";
  a.handleListenPasswordValidation=function(e){var t=e.action,n=e.data,r=void 0===n?{}:n;
  switch(a.sendMessageLock=!1,t){case H:a.handleSuccess();break;
  case J:console.log("err"),a.setState({isError:!0,errorText:r.message||"请求出错，请重试"});break;
  case W:a.setState({isError:!0,errorText:""});break;
  ${TARGET}
  default:return}};
`;

check("TARGET appears exactly once in fakeVendor", () => {
  assert.strictEqual(fakeVendor.split(TARGET).length - 1, 1);
});

check("bypass rewrites case G -> handleSuccess", () => {
  const { code, applied, mode } = patchVendorJs(fakeVendor, {
    enabled: true,
    mode: "bypass",
  });
  assert.strictEqual(applied, true);
  assert.strictEqual(mode, "bypass");
  assert.ok(code.includes("case G:a.handleSuccess();break;"));
  assert.ok(!code.includes(TARGET));
});

check("customPassword keeps failure fallback", () => {
  const { code } = patchVendorJs(fakeVendor, {
    enabled: true,
    mode: "customPassword",
    customPassword: "123456",
  });
  assert.ok(
    code.includes(`String(a.state.password)==="123456"`),
    "expected the comparison to be inlined"
  );
  assert.ok(code.includes(ORIGINAL_FAIL), "expected original failure body kept");
  assert.ok(!code.includes(TARGET));
});

check("unknown mode throws", () => {
  assert.throws(() => patchVendorJs(fakeVendor, { mode: "nope" }), /Unknown mode/);
});

check("missing target throws", () => {
  assert.throws(() => patchVendorJs("var x=1;", { mode: "bypass" }), /not found/);
});

console.log("lib/asar (round-trip)");

check("pack -> extract round-trips files and empty dirs", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hugopass-"));
  const src = path.join(tmp, "src");
  fs.mkdirSync(path.join(src, "public"), { recursive: true });
  fs.mkdirSync(path.join(src, "emptyDir"), { recursive: true });
  fs.writeFileSync(path.join(src, "main.js"), "console.log('hi');");
  fs.writeFileSync(path.join(src, "package.json"), '{"name":"x"}');
  fs.writeFileSync(path.join(src, "public", "vendor.js"), "中文 密码错误 content");

  const asarBuf = pack(src);
  const asarPath = path.join(tmp, "out.asar");
  fs.writeFileSync(asarPath, asarBuf);

  const out = path.join(tmp, "out");
  const count = extract(asarPath, out);

  assert.strictEqual(count, 3);
  assert.strictEqual(
    fs.readFileSync(path.join(out, "main.js"), "utf8"),
    "console.log('hi');"
  );
  assert.strictEqual(
    fs.readFileSync(path.join(out, "public", "vendor.js"), "utf8"),
    "中文 密码错误 content"
  );
  assert.ok(fs.existsSync(path.join(out, "emptyDir")), "empty dir should be kept");

  fs.rmSync(tmp, { recursive: true, force: true });
});

console.log("lib/verify");

check("crc32 of standard test vector", () => {
  assert.strictEqual(crc32Of(Buffer.from("123456789", "utf8")), 3421780262);
});

check("crc32HexLE little-endian formatting", () => {
  assert.strictEqual(crc32HexLE(3421780262), "2639f4cb");
  assert.strictEqual(crc32HexLE(2787933164), "ec7b2ca6");
});

check("updateVerifyJson updates the resources/app.asar entry", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hugopass-verify-"));
  const assistant = path.join(tmp, "SeewoServiceAssistant");
  fs.mkdirSync(path.join(assistant, "resources"), { recursive: true });

  const asarPath = path.join(assistant, "resources", "app.asar");
  fs.writeFileSync(asarPath, "fake asar");

  const verifyPath = path.join(assistant, "Verify.json");
  fs.writeFileSync(
    verifyPath,
    JSON.stringify(
      [
        { file_crc32: 2787933164, file_crc32_hex: "ec7b2ca6", file_path: "resources/app.asar" },
        { file_crc32: 123, file_crc32_hex: "0000007b", file_path: "other.dll" },
      ],
      null,
      3
    )
  );

  const updated = updateVerifyJson(asarPath, 1527680550);
  assert.strictEqual(updated, true);

  const list = JSON.parse(fs.readFileSync(verifyPath, "utf8"));
  const entry = list.find((e) => e.file_path === "resources/app.asar");
  assert.strictEqual(entry.file_crc32, 1527680550);
  assert.strictEqual(entry.file_crc32_hex, "268e0e5b");
  assert.strictEqual(list.find((e) => e.file_path === "other.dll").file_crc32, 123);
  assert.ok(fs.existsSync(verifyPath + ".orig"), "Verify.json backup should exist");

  fs.rmSync(tmp, { recursive: true, force: true });
});

console.log(failures === 0 ? "\nAll tests passed." : `\n${failures} test(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
