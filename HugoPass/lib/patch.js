// Patch the Seewo Hugo admin-password validation module inside `public/vendor.js`.
//
// How password validation works (renderer side, unchanged across the old and
// new versions):
//
//   1. User types a password and clicks confirm -> `handleConfirm` sends an IPC
//      message "adminPasswordValidation" with `{ password, ... }`.
//   2. The main process validates it (against the real admin password / server)
//      and replies with "adminPasswordValidationResult" carrying an action code.
//   3. `handleListenPasswordValidation` switches on the action:
//        H = passwordSuccess -> handleSuccess()  (unlock)
//        G = passwordFail    -> show "密码错误" + reset input
//        W = requestLimit    -> rate-limit message
//        J = requestError    -> generic error
//
// We only rewrite the `case G:` branch. That is enough to implement both
// features without re-implementing the whole (minified, webpack-bundled)
// module, and without depending on any module-id / variable that shifts
// between Seewo versions.

// The exact `case G:` branch, copied verbatim from vendor.js (v1.5.8).
// It ends at `break;` so it can be swapped out as one self-contained statement.
const TARGET = `case G:w.a.send("passwordInputLockError",{name:q,time:10}),a.setState({isError:!0,errorText:r.message||"密码错误"}),a.timeout=setTimeout(function(){a.sendMessageLock=!1,a.setState({password:"",isError:!1,errorText:""})},1e3);break;`;

// The original failure behavior (the body of `case G:` without the label and
// `break;`), reused as the `else` branch in custom-password mode.
const ORIGINAL_FAIL = `w.a.send("passwordInputLockError",{name:q,time:10}),a.setState({isError:!0,errorText:r.message||"密码错误"}),a.timeout=setTimeout(function(){a.sendMessageLock=!1,a.setState({password:"",isError:!1,errorText:""})},1e3)`;

/**
 * Rewrite the admin-password module in `vendorJs` according to `config`.
 *
 * @param {string} vendorJs - full contents of public/vendor.js (UTF-8)
 * @param {{enabled: boolean, mode: string, customPassword?: string}} config
 * @returns {{ code: string, applied: boolean, mode: string }}
 */
function patchVendorJs(vendorJs, config) {
  const mode = config.mode;

  if (!vendorJs.includes(TARGET)) {
    throw new Error(
      "Patch target not found in vendor.js. This Seewo Hugo version is " +
        "probably newer than the one this tool was written for; update TARGET " +
        "in lib/patch.js."
    );
  }

  let replacement;
  if (mode === "bypass") {
    // Any wrong password is treated as success -> unlock.
    replacement = `case G:a.handleSuccess();break;`;
  } else if (mode === "customPassword") {
    // The user's chosen password still unlocks; anything else fails as usual.
    const pw = String(config.customPassword ?? "");
    replacement =
      `case G:if(String(a.state.password)===${JSON.stringify(pw)})` +
      `{a.handleSuccess()}else{${ORIGINAL_FAIL}}break;`;
  } else {
    throw new Error(
      `Unknown mode "${mode}" (expected "bypass" or "customPassword").`
    );
  }

  return {
    code: vendorJs.replace(TARGET, replacement),
    applied: true,
    mode,
  };
}

module.exports = { patchVendorJs, TARGET, ORIGINAL_FAIL };
