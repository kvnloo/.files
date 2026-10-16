// Generated from Flow.bend by bend 2.0.37; do not hand-edit.
function word_to_u32(w) {
  let x = 0;
  for (let i = 0; w.$ === "WCon"; i++) {
    x |= Number(w.head) << i;
    w = w.tail;
  }
  return x >>> 0;
}

function u32_to_word(x) {
  let w = {$: "WNil"};
  for (let i = 31; i >= 0; i--) {
    w = {$: "WCon", head: ((x >>> i) & 1) === 1, tail: w};
  }
  return w;
}

function cmp_new(a, b) {
  return {$: a < b ? "LT"
    : a === b ? "EQ" : "GT"};
}

function nat_divmod(a, b) {
  return b === 0 ? {$: "Tuple", fst: 0, snd: a}
    : {$: "Tuple", fst: Math.trunc(a / b), snd: a % b};
}

function nat_chk(n) {
  if (n > 281474976710655) {
    throw "bend: a Nat past the largest immediate 2^48-1";
  }
  return n;
}

function nat_in(n) {
  return Number.isInteger(n) && n >= 0 && n <= 2 ** 53 ? n : nat_chk(1 / 0);
}

function f32_show(x) {
  if (x !== x) {
    return "nan";
  }
  if (!Number.isFinite(x) || Object.is(x, -0)) {
    return x < 0 ? "-inf"
      : x === 0 ? "-0" : "inf";
  }
  let s = "x";
  for (let p = 1; p <= 9 && f32_round(s) !== x; p += 1) {
    s = String(Number(x.toExponential(p - 1)));
  }
  return s;
}

function f32_bits(x) {
  return new Uint32Array(new Float32Array([x]).buffer)[0];
}

function f32_from_bits(u) {
  return new Float32Array(new Uint32Array([u]).buffer)[0];
}

function f32_read(s) {
  const re = /^[\t\n\v\f\r ]*[+-]?((\d+\.?\d*|\.\d+)(e[+-]?\d+)?|inf(inity)?|nan)$/i;
  const v = f32_round(s.replace(/inf\w*/i, "Infinity"));
  return re.test(s) ? {$: "Some", value: v} : {$: "None"};
}

const f32_round = function f32_round(s) {
  const d = Number(s);
  const a = Math.abs(d);
  const f = Math.fround(a);
  const g = 2 * a - Math.min(f, 2 ** 128);
  if (g === f || Math.fround(g) !== g || g === Infinity) {
    return Math.sign(d) * f;
  }
  let k = 0;
  while (a * 2 ** k % 1 !== 0) {
    k += 1;
  }
  const [, i, r, e] = /(\d*)\.?(\d*)(?:e([+-]?\d+))?$/i.exec(s);
  const n = Number(e ?? 0) - r.length;
  const x = BigInt(i + r) * 2n ** BigInt(k) * 10n ** BigInt(Math.max(n, 0));
  const y = BigInt(a * 2 ** k) * 10n ** BigInt(Math.max(-n, 0));
  return Math.sign(d) * (x === y || x > y !== g > f ? f : g);
};

function char_new(code) {
  if (code > 0x10FFFF || (code >= 0xD800 && code <= 0xDFFF)) {
    throw "bend: " + code + " is not a Unicode scalar value";
  }
  return String.fromCodePoint(code);
}

// Array
// =====

function array_new(d, v) {
  if (d > 31) {
    throw "bend: an array past the deepest block class 31";
  }
  return Array(2 ** d).fill(v);
}

function array_node(a, b) {
  if (a.length !== b.length) {
    throw "bend: runtime fail-stop";
  }
  return a.concat(b);
}

function array_rmw(a, i, f) {
  const at = i % a.length;
  const old = a[at];
  a[at] = f(old);
  return {$: "Tuple", fst: a, snd: old};
}

// Run
// ===

function run_tail(f, x) {
  return {$: "$JMP", f: f.j?.f === f ? f.j : f, x};
}

function run_clo(j) {
  const f = (x) => run_loop(j(x));
  f.j = j;
  j.f = f;
  return f;
}

function run_loop(r) {
  while (r !== null && typeof r === "object" && r.$ === "$JMP") {
    r = r.f(r.x);
  }
  return r;
}

function run_lib(f, n) {
  return (...a) => a.length < n ? run_lib((...b) => f(...a, ...b), n - a.length)
    : run_loop(f(...a));
}

// Effect
// ======

const $0eff = Object.create(null);

function io_eff(k, run) {
  if (arguments.length > 2) {
    throw new Error("bend: " + k + " takes no need: an effect that waits parks itself");
  }
  if (k in $0eff) {
    throw new Error("bend: two effects register " + k);
  }
  $0eff[k] = run;
}
// Program
// =======

function $main$() {
  return $Flow$058step$(($Flow$058initial$()), 0, 0);
}

function $Flow$058step$(_state_0, _event_0, _facts_0) {
  return $Flow$058route$(_event_0, _state_0, _facts_0);
}

function $Flow$058initial$() {
  return 0;
}

function $Flow$058route$(_event_0, _state_0, _facts_0) {
  if (_event_0 === 0) {
    return $Flow$058guard$(($Flow$058onboarding_rest$(_state_0)), true, _state_0, 0, 1, 1, 0);
  } else if (_event_0 === 1) {
    return $Flow$058status_result$((_state_0 === 1), ($Flow$058has$(_facts_0, 1)), ($Flow$058has$(_facts_0, 2)), _state_0);
  } else if (_event_0 === 2) {
    return $Flow$058guard$((_state_0 === 2), ($Flow$058has$(_facts_0, 4)), _state_0, 3, 3, 0, 3);
  } else if (_event_0 === 3) {
    return $Flow$058guard$((_state_0 === 2), true, _state_0, 0, 6, 0, 4);
  } else if (_event_0 === 4) {
    const _x_0 = (_state_0 === 3);
    const _x_1 = (_state_0 === 5);
    return $Flow$058guard$((_x_0 || _x_1), ($Flow$058has$(_facts_0, 4)), _state_0, 3, 4, 3, 0);
  } else if (_event_0 === 5) {
    const _x_2 = (_state_0 === 3);
    const _x_3 = (_state_0 === 5);
    return $Flow$058guard$((_x_2 || _x_3), ($Flow$058has$(_facts_0, 4)), _state_0, 3, 4, 4, 0);
  } else if (_event_0 === 6) {
    return $Flow$058module_result$((_state_0 === 4), ($Flow$058has$(_facts_0, 1)), ($Flow$058has$(_facts_0, 8)), _state_0);
  } else if (_event_0 === 7) {
    return $Flow$058guard$((_state_0 === 3), ($Flow$058has$(_facts_0, 3)), _state_0, 16, 5, 0, 8);
  } else if (_event_0 === 8) {
    const _x_4 = ($Flow$058onboarding_rest$(_state_0));
    const _x_5 = (_state_0 === 22);
    return $Flow$058guard$((_x_4 || _x_5), ($Flow$058has$(_facts_0, 20)), _state_0, 4, 10, 0, 9);
  } else if (_event_0 === 9) {
    const _x_6 = (_state_0 === 10);
    const _x_7 = (_state_0 === 20);
    return $Flow$058guard$((_x_6 || _x_7), ($Flow$058has$(_facts_0, 96)), _state_0, 6, 11, 5, 0);
  } else if (_event_0 === 10) {
    return $Flow$058preflight_result$((_state_0 === 11), ($Flow$058has$(_facts_0, 1)), _state_0, _facts_0);
  } else if (_event_0 === 11) {
    return $Flow$058apply_request$((_state_0 === 14), _state_0, _facts_0);
  } else if (_event_0 === 12) {
    const _x_8 = (_state_0 === 13);
    const _x_9 = (_state_0 === 23);
    return $Flow$058startup_result$((_x_8 || _x_9), ($Flow$058has$(_facts_0, 1)), ($Flow$058has$(_facts_0, 134246400)), _state_0);
  } else if (_event_0 === 13) {
    return $Flow$058guard$((_state_0 === 14), ($Flow$058has$(_facts_0, 65604)), _state_0, 18, 15, 7, 0);
  } else if (_event_0 === 14) {
    return $Flow$058guard$((_state_0 === 15), ($Flow$058has$(_facts_0, 32769)), _state_0, 2, 16, 0, 15);
  } else if (_event_0 === 15) {
    return $Flow$058guard$((_state_0 === 16), ($Flow$058has$(_facts_0, 196676)), _state_0, 19, 17, 8, 0);
  } else if (_event_0 === 16) {
    return $Flow$058guard$((_state_0 === 17), ($Flow$058has$(_facts_0, 3932161)), _state_0, 13, 18, 0, 17);
  } else if (_event_0 === 17) {
    return $Flow$058guard$((_state_0 === 18), ($Flow$058has$(_facts_0, 4194305)), _state_0, 14, 19, 0, 18);
  } else if (_event_0 === 18) {
    return $Flow$058guard$(($Flow$058server_state$(_state_0)), ($Flow$058has$(_facts_0, 1)), _state_0, 2, 20, 0, 19);
  } else if (_event_0 === 19) {
    return $Flow$058guard$((_state_0 === 20), ($Flow$058has$(_facts_0, 68)), _state_0, 20, 20, 9, 0);
  } else if (_event_0 === 20) {
    return $Flow$058guard$((_state_0 === 20), ($Bool$and$(($Flow$058has$(_facts_0, 301995108)), ($Bool$not$(($Flow$058has$(_facts_0, 8192)))))), _state_0, 21, 23, 10, 0);
  } else if (_event_0 === 21) {
    const _x_10 = ($Flow$058server_state$(_state_0));
    const _x_11 = (_state_0 === 20);
    return $Flow$058guard$((_x_10 || _x_11), ($Flow$058has$(_facts_0, 25165892)), _state_0, 22, 21, 11, 0);
  } else if (_event_0 === 22) {
    return $Flow$058guard$((_state_0 === 21), ($Flow$058has$(_facts_0, 67108865)), _state_0, 2, 22, 0, 23);
  } else {
    return $Flow$058denied$(_state_0, 23);
  }
}

function $Flow$058guard$(_phase_0, _facts_0, _state_0, _reason_0, _next_0, _action_0, _established_0) {
  if (!_phase_0) {
    return $Flow$058denied$(_state_0, 1);
  } else {
    if (!_facts_0) {
      return $Flow$058denied$(_state_0, _reason_0);
    } else {
      return $Flow$058allowed$(_next_0, 0, _action_0, _established_0);
    }
  }
}

function $Flow$058onboarding_rest$(_state_0) {
  const _x_0 = (_state_0 === 0);
  const _x_1 = (_state_0 === 2);
  const _x_2 = (_x_0 || _x_1);
  const _x_3 = (_state_0 === 3);
  const _x_4 = (_x_2 || _x_3);
  const _x_5 = (_state_0 === 5);
  const _x_6 = (_x_4 || _x_5);
  const _x_7 = (_state_0 === 6);
  return (_x_6 || _x_7);
}

function $Flow$058status_result$(_phase_0, _observed_0, _complete_0, _state_0) {
  if (!_phase_0) {
    return $Flow$058denied$(_state_0, 1);
  } else {
    if (!_observed_0) {
      return $Flow$058denied$(_state_0, 2);
    } else {
      if (!_complete_0) {
        return $Flow$058allowed$(2, 0, 2, 2);
      } else {
        return $Flow$058allowed$(5, 0, 0, 2);
      }
    }
  }
}

function $Flow$058has$(_facts_0, _mask_0) {
  const _x_0 = ((_facts_0 & _mask_0) >>> 0);
  return (_x_0 === _mask_0);
}

function $Flow$058module_result$(_phase_0, _observed_0, _succeeded_0, _state_0) {
  if (!_phase_0) {
    return $Flow$058denied$(_state_0, 1);
  } else {
    if (!_observed_0) {
      return $Flow$058denied$(_state_0, 2);
    } else {
      if (!_succeeded_0) {
        return $Flow$058allowed$(3, 15, 0, 7);
      } else {
        return $Flow$058allowed$(3, 0, 0, 7);
      }
    }
  }
}

function $Flow$058preflight_result$(_phase_0, _observed_0, _state_0, _facts_0) {
  if (!_phase_0) {
    return $Flow$058denied$(_state_0, 1);
  } else {
    if (!_observed_0) {
      return $Flow$058denied$(_state_0, 2);
    } else {
      return $Flow$058preflight_reason$(($Flow$058preflight_gates$(($Flow$058has$(_facts_0, 32)), ($Flow$058has$(_facts_0, 64)), ($Flow$058has$(_facts_0, 128)), ($Flow$058has$(_facts_0, 256)), ($Flow$058has$(_facts_0, 512)), ($Flow$058has$(_facts_0, 1024)), ($Flow$058has$(_facts_0, 2048)))), ($Flow$058has$(_facts_0, 4096)), ($Flow$058has$(_facts_0, 24576)));
    }
  }
}

function $Flow$058apply_request$(_already_ready_0, _state_0, _facts_0) {
  if (_already_ready_0) {
    return $Flow$058guard$(true, ($Bool$and$(($Bool$and$(($Flow$058has$(_facts_0, 4084)), ($Flow$058has$(_facts_0, 4096)))), ($Flow$058has$(_facts_0, 24576)))), _state_0, 17, 14, 0, 0);
  } else {
    return $Flow$058guard$((_state_0 === 12), ($Bool$and$(($Flow$058has$(_facts_0, 4084)), ($Bool$not$(($Flow$058has$(_facts_0, 4096)))))), _state_0, 17, 13, 6, 0);
  }
}

function $Flow$058startup_result$(_phase_0, _observed_0, _ready_0, _state_0) {
  if (!_phase_0) {
    return $Flow$058denied$(_state_0, 1);
  } else {
    if (!_observed_0) {
      return $Flow$058denied$(_state_0, 2);
    } else {
      if (!_ready_0) {
        return $Flow$058allowed$(20, 12, 0, 13);
      } else {
        return $Flow$058allowed$(14, 0, 0, 13);
      }
    }
  }
}

function $Flow$058server_state$(_state_0) {
  const _x_0 = (_state_0 === 12);
  const _x_1 = (_state_0 === 13);
  const _x_2 = (_x_0 || _x_1);
  const _x_3 = (_state_0 === 14);
  const _x_4 = (_x_2 || _x_3);
  const _x_5 = (_state_0 === 15);
  const _x_6 = (_x_4 || _x_5);
  const _x_7 = (_state_0 === 16);
  const _x_8 = (_x_6 || _x_7);
  const _x_9 = (_state_0 === 17);
  const _x_10 = (_x_8 || _x_9);
  const _x_11 = (_state_0 === 18);
  const _x_12 = (_x_10 || _x_11);
  const _x_13 = (_state_0 === 19);
  const _x_14 = (_x_12 || _x_13);
  const _x_15 = (_state_0 === 23);
  return (_x_14 || _x_15);
}

function $Bool$and$(_a_0, _b_0) {
  if (!_a_0) {
    return false;
  } else {
    return _b_0;
  }
}

function $Bool$not$(_b_0) {
  if (!_b_0) {
    return true;
  } else {
    return false;
  }
}

function $Flow$058denied$(_state_0, _reason_0) {
  const _x_0 = (Math.imul(_reason_0, 128) >>> 0);
  return ((_state_0 + _x_0) >>> 0);
}

function $Flow$058allowed$(_state_0, _reason_0, _action_0, _established_0) {
  const _x_0 = ((_state_0 + 64) >>> 0);
  const _x_1 = (Math.imul(_reason_0, 128) >>> 0);
  const _x_2 = ((_x_0 + _x_1) >>> 0);
  const _x_3 = (Math.imul(_action_0, 8192) >>> 0);
  const _x_4 = ((_x_2 + _x_3) >>> 0);
  const _x_5 = (Math.imul(_established_0, 262144) >>> 0);
  return ((_x_4 + _x_5) >>> 0);
}

function $Flow$058preflight_reason$(_reason_0, _managed_0, _ready_0) {
  return $Flow$058preflight_decision$((_reason_0 === 0), _managed_0, _ready_0, _reason_0);
}

function $Flow$058preflight_gates$(_host_0, _admin_0, _storage_0, _network_0, _firewall_0, _ownership_0, _passed_0) {
  if (!_host_0) {
    return 5;
  } else {
    if (!_admin_0) {
      return 6;
    } else {
      if (!_storage_0) {
        return 7;
      } else {
        if (!_network_0) {
          return 8;
        } else {
          if (!_firewall_0) {
            return 9;
          } else {
            if (!_ownership_0) {
              return 10;
            } else {
              if (!_passed_0) {
                return 11;
              } else {
                return 0;
              }
            }
          }
        }
      }
    }
  }
}

function $Flow$058preflight_decision$(_passed_0, _managed_0, _ready_0, _reason_0) {
  if (_passed_0) {
    if (!_managed_0) {
      return $Flow$058allowed$(12, 0, 0, 11);
    } else {
      if (!_ready_0) {
        return $Flow$058allowed$(20, 12, 0, 11);
      } else {
        return $Flow$058allowed$(14, 0, 0, 11);
      }
    }
  } else {
    return $Flow$058allowed$(20, _reason_0, 0, 11);
  }
}

// Cli
// ===

let cli_args = [];

function cli(argv) {
  cli_args.push(argv[0]);
  for (let i = 1; i < argv.length; i += 1) {
    if (argv[i] === "--") {
      cli_args.push(...argv.slice(i + 1));
      break;
    } else if (argv[i] === "--bend-help") {
      io_out(1, io_bytes("usage: " + argv[0] + "\n"));
      process.exit(0);
    } else if (argv[i] === "--threads" || argv[i] === "--gpu") {
      i += 1;
    } else {
      cli_args.push(argv[i]);
    }
  }
}

// Show
// ====

// show_val prints a pure main's value as term_show does (see show_main);
// chain is the bracket it continues, or 0.

function show_chr(s, q) {
  const c = s.codePointAt(0);
  const k = { 10: "n", 9: "t", 13: "r", 0: "0", 92: "\\" }[c]
    ?? (s === q ? q : null);
  return k !== null ? "\\" + k : c < 32 || c === 127
    || (c >= 0xD800 && c <= 0xDFFF) ? "\\u{" + c.toString(16) + "}" : s;
}

function show_val(D, d, v, chain) {
  if (D[d] === 7) {
    const fs = Object.values(typeof v === "boolean"
      ? { $: v ? "True" : "False" } : v);
    let a = d + 3;
    for (; D[a + 1] !== fs[0]; a += 4 + 2 * D[a + 2]) {}
    const o = "{[("[D[a + 3]];
    let s = o === "{" ? fs[0] + "{" : chain === o ? "" : o;
    for (const [j, f] of fs.slice(1).entries()) {
      if (o === "[" ? j === 0 && chain === o : j > 0) {
        s += ", ";
      }
      s += show_val(D, D[a + 5 + 2 * j], f, j === 1 && o !== "{" ? o : 0);
    }
    return o === "{" || chain !== o ? s + "}])"[D[a + 3]] : s;
  }
  return D[d] === 0 ? String(v)
    : D[d] === 1 ? f32_show(v).replace(/^-?\d+(?=e|$)/, "$&.0")
    : D[d] === 2 ? v + "n"
    : D[d] === 3 ? "'" + show_chr(v, "'") + "'"
    : D[d] === 4 ? "\"" + [...v].map((c) => show_chr(c, "\"")).join("") + "\""
    : D[d] === 5 ? "{==}"
    : "[" + v.map((x) => show_val(D, D[d + 1], x, 0)).join(", ") + "]";
}

// Io
// ==

// Apple arm64 passes variadic fcntl flags on the stack, so io_sys
// binds fcntl there with the flags as the ninth fixed argument. A
// parked effect waits for fd (a write when out) or until at
// (performance.now()), either one undefined when unused; once due, io_wait
// calls more at once, as C calls pack, and resumes k with its value, while
// undefined parks it again. The waits stay in deadline order, as io_park
// does in C.

function io_exit(main, show) {
  try {
    if (show !== null) {
      io_out(1, io_bytes(show_val(show, 0, run_loop(main()), 0) + "\n"));
      process.exit(0);
    }
    process.exit(io_run(main));
  } catch (e) {
    io_errs(String(e));
    process.exit(1);
  }
}

function io_out(fd, data) {
  const fs = require("fs");
  let at = 0;
  while (at < data.length) {
    try {
      at += fs.writeSync(fd, data, at, data.length - at);
    } catch (e) {
      if (e.code === "EAGAIN" || e.code === "EINTR") {
        continue;
      }
      // Bun ignores SIGPIPE until a listener comes and goes.
      if (e.code === "EPIPE") {
        process.on("SIGPIPE", () => {}).removeAllListeners("SIGPIPE")
          .kill(process.pid, "SIGPIPE");
      }
      try {
        fs.writeSync(2, "bend: a short write on a standard stream\n");
      } catch (o) {
      }
      process.exit(1);
    }
  }
}

function io_errs(message) {
  io_out(2, io_bytes(message + "\n"));
}

function io_sys() {
  if (globalThis.BEND_SYS === undefined) {
    const ffi = require("bun:ffi");
    const mac = process.platform === "darwin";
    const err = mac ? "__error" : "__errno_location";
    const sel = mac ? "select$DARWIN_EXTSN" : "select";
    const T = { i: "i32", u: "u32", U: "u64", I: "i64", p: "ptr",
      c: "cstring" };
    const vari = mac && process.arch === "arm64";
    const lib = ffi.dlopen(mac ? "libSystem.dylib" : "libc.so.6",
      Object.fromEntries(("socket:iii>i bind:ipu>i listen:ii>i connect:ipu>i"
        + " accept:ipp>i send:ipUi>I recv:ipUi>I read:ipU>I pread:ipUI>I"
        + " sendto:ipUipu>I recvfrom:ipUipp>I close:i>i setsockopt:iiipu>i"
        + " " + sel + ":ipppp>i"
        + (vari ? " fcntl:iiiiiiiii>i" : " fcntl:iii>i") + " getsockopt:iiipp>i"
        + " strerror:i>c " + err + ":>p").split(" ").map((s) => {
        const [name, args, ret] = s.split(/[:>]/);
        return [name, { args: [...args].map((a) => T[a]), returns: T[ret] }];
      }))).symbols;
    const fcntl = (fd, cmd, arg) => vari
      ? lib.fcntl(fd, cmd, 0, 0, 0, 0, 0, 0, arg)
      : lib.fcntl(fd, cmd, arg);
    globalThis.BEND_SYS = { ...lib, fcntl, select: lib[sel],
      ptr: ffi.ptr, mac,
      errno: () => ffi.read.i32(lib[err](), 0) };
  }
  return globalThis.BEND_SYS;
}

// strerror needs bun:ffi; a host without it (node) gets the bare errno.
function io_strerror(code) {
  try {
    return String(io_sys().strerror(code));
  } catch (_) {
    return "errno " + code;
  }
}

function io_fail(code, ...rest) {
  const err = io_tup(code >>> 0, io_strerror(code));
  return { $: "Fail", error: io_tup(err, ...rest) };
}

function io_done(value) {
  return { $: "Done", value };
}

function io_until(ms) {
  return performance.now() + Number(ms);
}

function io_late(at) {
  return at !== undefined && performance.now() >= at;
}

function io_ready(at, r) {
  return at === undefined ? r : { $: "Ready", value: r };
}

function io_tup(...xs) {
  return xs.reduceRight((snd, fst) => ({ $: "Tuple", fst, snd }));
}

function io_bytes(text) {
  return new TextEncoder().encode(text);
}

function io_text(b, n) {
  return new TextDecoder("utf-8", { ignoreBOM: true }).decode(b.subarray(0, n));
}

// Bytes cross as they are (0..255), one List cell each, with no UTF-8 in
// either direction; io_unlist answers null if a value is past 255.
function io_list(b, n) {
  let xs = { $: "Nil" };
  while (n > 0) {
    xs = { $: "Con", head: b[--n], tail: xs };
  }
  return xs;
}

function io_unlist(xs) {
  const b = [];
  for (; xs.$ === "Con"; xs = xs.tail) {
    b.push(xs.head);
  }
  return b.some((x) => x > 255) ? null : Uint8Array.from(b);
}

function io_addr(host, port) {
  const part = host.split(".");
  const deci = (p) => /^(0|[1-9]\d{0,2})$/.test(p) && Number(p) < 256;
  if (port > 65535 || part.length !== 4 || !part.every(deci)) {
    return null;
  }
  const b = new Uint8Array(16);
  const head = io_sys().mac ? [16, 2] : [2, 0];
  b.set([...head, port >> 8, port & 255, ...part.map(Number)]);
  return b;
}

function io_push(fun, arg, fresh) {
  const io = globalThis.BEND_IO;
  io.runs.push({ fun, arg });
  io.live += fresh ? 1 : 0;
}

function io_wait(io, block) {
  const soon = io.waits[0]?.at ?? Infinity;
  const ms = !block ? 0 : soon === Infinity ? -1
    : Math.max(0, Math.ceil(soon - performance.now()));
  const fds = io.waits.filter((w) => w.fd !== undefined);
  const top = fds.reduce((m, w) => Math.max(m, w.fd), 0);
  const len = (top >> 6 << 3) + 8;
  const set = new Uint8Array(2 * len);
  const at = (w) => (w.out ? len : 0) + (w.fd >> 3);
  for (const w of fds) {
    set[at(w)] |= 1 << (w.fd & 7);
  }
  const tv = new BigInt64Array([BigInt(ms / 1000 | 0),
    BigInt(ms % 1000 * 1000)]);
  const sys = io_sys();
  if (sys.select(top + 1, sys.ptr(set), sys.ptr(set, len), null,
    ms < 0 ? null : sys.ptr(tv)) < 0) {
    if (sys.errno() !== 4) {
      throw "bend: the poller failed";
    }
    set.fill(0);
  }
  const now = performance.now();
  const due = (w) => w.at <= now || w.fd !== undefined
    && set[at(w)] & 1 << (w.fd & 7);
  const todo = io.waits;
  io.waits = todo.filter((w) => !due(w));
  for (const w of todo.filter(due)) {
    const x = w.more();
    if (x !== undefined) {
      io_push(w.k, x, false);
    }
  }
}

function io_park_on(fd, out, k, more, at) {
  const ws = globalThis.BEND_IO.waits;
  const i = ws.findLastIndex((w) => (w.at ?? Infinity) <= (at ?? Infinity));
  ws.splice(i + 1, 0, { fd, out, k, more, at });
}

function io_run(m) {
  const io = { runs: [], live: 0, waits: [] };
  globalThis.BEND_IO = io;
  try {
    io_push(run_loop(m()), (x) => ({ $: "Emit", value: x }), true);
    let look = 0;
    for (let n = 0;; n += 1) {
      if (io.runs.length === 0) {
        if (io.live === 0) {
          return 0;
        }
        if (io.waits.length === 0) {
          io_errs("bend: deadlock: every computation waits on a channel");
          return 1;
        }
        io_wait(io, true);
        continue;
      }
      if ((n & 63) === 0 && io.waits.length > 0) {
        const now = performance.now();
        if (now >= look || io.waits[0].at <= now) {
          look = now + 10;
          io_wait(io, false);
        }
      }
      const s = io.runs.shift();
      let op = s.fun(s.arg);
      while (op !== undefined) {
        if (op.$ === "Emit") {
          io.live -= 1;
          break;
        }
        if (op.$ === "Halt" || op.$ === "Exit") {
          if (op.$ === "Halt") io_errs(op.message);
          if (op.code > 255) {
            io_errs("bend: exit code must be in 0..255");
            return 1;
          }
          return op.code;
        }
        const run = $0eff[op.$];
        if (run === undefined) {
          throw "bend: no effect registers " + op.$;
        }
        const x = run(...op.args, op.kont);
        if (x === undefined) {
          break;
        }
        op = op.kont(x);
      }
    }
  } catch (e) {
    throw e instanceof RangeError ? "bend: memory fault (machine stack overflow?)" : e;
  }
}

export const bendInitial = () => run_loop($Flow$058initial$());
export const bendStep = (state, event, facts) => run_loop($Flow$058step$(state, event, facts));
export const bendMetadata = {"schema":1,"scope":"Finite control abstraction of .files onboarding and a distinct opt-in single-node K3s lifecycle. Requests never execute commands. General onboarding completion does not imply K3s installation; K3s entry switches the displayed lifecycle, not the machine's onboarding record. Repeated module selection abstracts the three recommended modules and four optional modules; native scripts retain their own details.","trustBoundary":"Every fact is externally supplied for replay. Bend checks phase and supplied permission/evidence predicates, not their truth, freshness, identity binding, OS execution, firewall enforcement or Factory authority. Synthetic scenarios are not deployment receipts. No invariant theorem/proof suite is claimed; compilation/typechecking alone is not an invariant proof.","groups":[{"id":"onboarding","title":"General onboarding · shared modules"},{"id":"k3s","title":"K3s · separate explicit opt-in"},{"id":"recovery","title":"Review / destructive rollback"}],"states":[{"id":0,"group":"onboarding","title":"Open checkout","summary":"No status observation yet. Phone is a controller; this diagram performs no native setup.","citations":[{"path":"AGENTS.md","symbol":"First contact"},{"path":"README.md","symbol":"Setup (two methods)"}]},{"id":1,"group":"onboarding","title":"Status requested","summary":"Read onboard status --json; await an external result. Status request establishes no completion.","citations":[{"path":"scripts/onboard","symbol":"cmd_status"}]},{"id":2,"group":"onboarding","title":"Ask before setup","summary":"Recommended baseline incomplete: ask explicitly whether to run onboarding.","citations":[{"path":"AGENTS.md","symbol":"First contact"},{"path":"scripts/onboard","symbol":"cmd_offer"}]},{"id":3,"group":"onboarding","title":"Select one module","summary":"Explicitly approved guided setup. Select core-links, fonts, agent-skills, or separately confirmed optional agent-tools/tailnet-ssh/nix-home/audio-evolution. K3s is not a module.","citations":[{"path":"scripts/onboard","symbol":"run_module / interactive_menu / cmd_install"},{"path":"docs/SETUP.md","symbol":"Modules"}]},{"id":4,"group":"onboarding","title":"Module requested","summary":"Await result of only the selected module; success bookkeeping is not full external verification.","citations":[{"path":"scripts/onboard","symbol":"run_module"},{"path":"scripts/lib/onboard-common.sh","symbol":"onboard_mark_module"}]},{"id":5,"group":"onboarding","title":"Recommended complete","summary":"External status reports core-links + fonts + agent-skills done or done-inferred. Do not automatically re-offer; doctor/optional modules remain available. This says nothing about K3s.","citations":[{"path":"scripts/onboard","symbol":"recommended_done / cmd_status"},{"path":"AGENTS.md","symbol":"What recommended setup means"}]},{"id":6,"group":"onboarding","title":"Setup deferred","summary":"User declined onboarding. No module runs; later explicit setup remains possible.","citations":[{"path":"scripts/onboard","symbol":"cmd_offer"}]},{"id":10,"group":"k3s","title":"K3s opt-in recorded","summary":"Separate user choice only. Phone/Android/proot and MacBook cannot host this server; use confirmed native Groot desktop and keep credentials there.","citations":[{"path":"docs/k3s/ONBOARDING.md","symbol":"Phone first / Desktop server / MacBook client"},{"path":"README.md","symbol":"Optional CPU-only K3s"}]},{"id":11,"group":"k3s","title":"Read-only preflight requested","summary":"Authenticated native host runs --check with discovered private node IP and reviewed firewall policy. No downloads, staging, writes or service restart.","citations":[{"path":"scripts/setup-k3s.sh","symbol":"main / check_host / check_paths / check_network / check_firewall"}]},{"id":12,"group":"k3s","title":"Fresh install eligible","summary":"Supplied preflight observation passed all gates, with no changed/foreign installation. Still not installed; explicit --apply required with same approved flags. Facts must be refreshed externally before apply.","citations":[{"path":"scripts/setup-k3s.sh","symbol":"check_existing / main"}]},{"id":13,"group":"k3s","title":"Apply requested · not success","summary":"Request pinned verified installer/binary, private staging and atomic config publication. Ownership marker may survive startup failure; request alone proves no installation/readiness.","citations":[{"path":"scripts/setup-k3s.sh","symbol":"apply_install / write_state"},{"path":"config/k3s/config.yaml","symbol":"private CPU-only single-server defaults"}]},{"id":14,"group":"k3s","title":"Managed API ready observed","summary":"External observation binds matching managed state, active service and ready private API. An exact managed rerun checks without reinstall/restart. Namespace boundary is not applied automatically.","citations":[{"path":"scripts/setup-k3s.sh","symbol":"verify_managed / apply_install"},{"path":"docs/k3s/ONBOARDING.md","symbol":"Access and manifests"}]},{"id":15,"group":"k3s","title":"Boundary apply requested","summary":"Separately approved explicit-context namespace manifest apply. Configured desired state is not actual enforcement evidence.","citations":[{"path":"docs/k3s/ONBOARDING.md","symbol":"Access and manifests"},{"path":"config/k3s/manifests/boundary.json","symbol":"List.items"}]},{"id":16,"group":"k3s","title":"Boundary applied observed","summary":"Shared namespace/SA/quota/LimitRange/PSA/default-deny objects observed. Six-Pod quota and ingress/egress enforcement still need runtime controls.","citations":[{"path":"config/k3s/manifests/boundary.json","symbol":"worker-guardrail / deny-all-worker-traffic"},{"path":"scripts/smoke-k3s.sh","symbol":"live prerequisite checks"}]},{"id":17,"group":"k3s","title":"Bounded smoke requested","summary":"Approved quiet namespace and explicit context; uniquely named probes/Job, scoped cleanup only, no Factory lease or authorization. Capture evidence privately.","citations":[{"path":"scripts/smoke-k3s.sh","symbol":"argument parser / create / owned resources"},{"path":"config/k3s/manifests/cpu-example-job.json","symbol":"spec / securityContext / resources"}]},{"id":18,"group":"k3s","title":"Runtime evidence observed · await TTL","summary":"Job Complete alone is insufficient: supplied retained evidence includes source hashes/context, successful container results for EVERY captured Pod, actual imageID, exit/node/timestamps/logs, verified live quota AND LimitRange, seventh-Pod denial and independent network controls. Cleanup under the reviewed live TTL remains unobserved.","citations":[{"path":"scripts/smoke-k3s.sh","symbol":"live prerequisite checks / source / quota_seventh_pod_denied / network controls / container_result"}]},{"id":19,"group":"k3s","title":"Bounded runtime acceptance","summary":"Retained evidence plus matching reviewed live TTL and Job AND dependent Pod disappearance observed without helper deletion. This is cleanup under that TTL configuration, not an exclusive-cause controller audit. Infrastructure smoke only: no universal network/sandbox guarantee, production deployment, contribution acceptance or Factory authorization.","citations":[{"path":"scripts/smoke-k3s.sh","symbol":"live Job TTL check / ttl_cleanup_verified"},{"path":"docs/k3s/ONBOARDING.md","symbol":"Bounded smoke and evidence"}]},{"id":20,"group":"recovery","title":"Blocked / manual review","summary":"Storage/auth/network/firewall/host failure, partial startup, changed/foreign ownership or later drift. No overwrite, adoption, automatic cleanup or restart. Retain ownership marker and working Tern access.","citations":[{"path":"scripts/setup-k3s.sh","symbol":"check_existing / verify_managed"},{"path":"docs/k3s/ONBOARDING.md","symbol":"Recovery and rollback"}]},{"id":21,"group":"recovery","title":"Destructive rollback requested","summary":"Only explicit destructive approval after backup, Factory workload stop and killall/uninstall network impact review. Exact approved K3S_DATA_DIR; never namespace deletion as smoke cleanup.","citations":[{"path":"docs/k3s/ONBOARDING.md","symbol":"Recovery and rollback"}]},{"id":22,"group":"recovery","title":"Rollback observed","summary":"External observation reports approved teardown complete. No automatic reinstall or assertion host networking/other services are healthy.","citations":[{"path":"docs/k3s/ONBOARDING.md","symbol":"Recovery and rollback"}]},{"id":23,"group":"recovery","title":"Reviewed start requested","summary":"Exact owned inactive service only, cause reviewed and start explicitly approved. Await new startup/API observation; --apply rerun is never a recovery restart.","citations":[{"path":"docs/k3s/ONBOARDING.md","symbol":"Recovery and rollback"},{"path":"scripts/setup-k3s.sh","symbol":"verify_managed"}]}],"events":[{"id":0,"title":"Request onboarding status"},{"id":1,"title":"Observe onboarding status"},{"id":2,"title":"Approve onboarding"},{"id":3,"title":"Decline onboarding"},{"id":4,"title":"Run selected recommended module"},{"id":5,"title":"Run selected optional module"},{"id":6,"title":"Observe selected module result"},{"id":7,"title":"Observe recommended completion"},{"id":8,"title":"Opt into distinct K3s lifecycle"},{"id":9,"title":"Request read-only K3s preflight"},{"id":10,"title":"Observe K3s preflight"},{"id":11,"title":"Explicitly apply K3s"},{"id":12,"title":"Observe managed startup / API"},{"id":13,"title":"Separately apply boundary manifests"},{"id":14,"title":"Observe boundary objects applied"},{"id":15,"title":"Request bounded runtime smoke"},{"id":16,"title":"Observe Job and runtime controls"},{"id":17,"title":"Observe cleanup under reviewed live TTL"},{"id":18,"title":"Observe partial / changed / foreign state"},{"id":19,"title":"Request private manual review"},{"id":20,"title":"Explicitly start reviewed inactive service"},{"id":21,"title":"Approve destructive rollback"},{"id":22,"title":"Observe approved rollback complete"}],"facts":[{"key":"observed","bit":0,"title":"External observation supplied","description":"Host result supplied by observer, not manufactured by a request."},{"key":"recommendedComplete","bit":1,"title":"Recommended status complete","description":"onboard status reports core-links/fonts/agent-skills done or done-inferred; not OS-wide health."},{"key":"userApproved","bit":2,"title":"Explicit approval for this action","description":"Scoped selection/consent, not blanket authorization for later optional or destructive actions."},{"key":"moduleSucceeded","bit":3,"title":"Selected module succeeded"},{"key":"explicitK3sOptIn","bit":4,"title":"Separate K3s opt-in"},{"key":"nativeHost","bit":5,"title":"Native desktop host verified","description":"Supported Linux/systemd x86_64, not Android/proot/container/laptop; cgroup v2, memory and tools satisfy bootstrap."},{"key":"adminAuthenticated","bit":6,"title":"Approved host admin authenticated","description":"Human-approved desktop root/sudo session; no hidden escalation or credential copies."},{"key":"storageSafe","bit":7,"title":"Root/kubelet/data storage gates passed","description":"Each byte filesystem >5% free plus 1 GiB reserve; inode >5% plus 1000 (Btrfs zero-inode special reporting); dedicated path reviewed. No deletion implicitly approved."},{"key":"networkReviewed","bit":8,"title":"Private address / network reviewed","description":"Assigned private node IP, CIDRs/routes/ports and tailnet ACL/netfilter ordering reviewed; UFW alone is not tailnet isolation."},{"key":"firewallReviewed","bit":9,"title":"Supported UFW policy verified","description":"Active deny incoming/allow outgoing; dedicated cni0 rules and reviewed narrow SSH; preserve access, never auto-reset."},{"key":"ownershipSafe","bit":10,"title":"Fresh or exact managed ownership safe","description":"No foreign/partial state, changed config/binary/service/settings or competing agent. No silent adoption."},{"key":"preflightPassed","bit":11,"title":"Full read-only preflight passed"},{"key":"managedExact","bit":12,"title":"Exact managed installation verified","description":"Matching ownership/hashes/permissions/settings; ownership marker alone insufficient."},{"key":"serviceActive","bit":13,"title":"Service active/enabled observed"},{"key":"apiReady","bit":14,"title":"Private API readiness observed"},{"key":"boundaryApplied","bit":15,"title":"Live boundary apply result observed","description":"Desired manifests exist in checkout is NOT this fact; enforcement is tested separately."},{"key":"contextExplicit","bit":16,"title":"Explicit verified kubectl context"},{"key":"namespaceQuiet","bit":17,"title":"Quiet namespace window approved","description":"Existing authority paused submissions; no nonterminal workers, no invented scheduler/lease."},{"key":"jobComplete","bit":18,"title":"CPU Job Complete observed"},{"key":"evidenceRetained","bit":19,"title":"Runtime evidence retained privately","description":"Actual source hashes/dirty commit/context, timestamped logs, full Job/Pod status, actual imageID, zero exit, node and timing bound to this run. EVERY captured Pod supplies successful container results; live ResourceQuota AND LimitRange match the shared boundary. Missing status or drifted limits invalidates this fact. Never secrets in Git."},{"key":"quotaVerified","bit":20,"title":"Six-held / seventh-Pod quota verified"},{"key":"networkControlsVerified","bit":21,"title":"Independent network controls verified","description":"Real positive TCP connectivity; ingress and egress negative controls independently timeout against a running server; restored allowance restores connectivity. Not universal isolation."},{"key":"ttlVerified","bit":22,"title":"Job AND Pod cleanup under reviewed TTL","description":"Live Job TTL matches the reviewed fixture; helper observes Job AND dependent Pod disappearance without deleting them itself. Not an exclusive-cause TTL-controller audit. Manual cleanup, Job-only deletion or missing/changed live TTL does not satisfy this fact."},{"key":"destructiveApproved","bit":23,"title":"Explicit destructive teardown approval"},{"key":"backupAndWorkloadsReviewed","bit":24,"title":"Backup / workload / uninstall impact reviewed","description":"Backups outside Git; workloads stopped through Factory; killall/uninstall host-wide network effects and exact approved K3S_DATA_DIR reviewed."},{"key":"reviewComplete","bit":25,"title":"Root cause reviewed with owner"},{"key":"rollbackComplete","bit":26,"title":"Approved teardown completion observed"},{"key":"installRecorded","bit":27,"title":"Managed installation ownership observed","description":"Explicit installation observation, not inferred from request; readiness additionally needs exact managed verification."},{"key":"serviceInactive","bit":28,"title":"Owned service inactive observed","description":"For explicit reviewed start only; no automatic restart or recovery apply."}],"actions":[{"id":0,"title":"No native action"},{"id":1,"title":"Read ./scripts/onboard status --json"},{"id":2,"title":"Ask: want to run onboarding setup?"},{"id":3,"title":"Run only selected core-links / fonts / agent-skills module"},{"id":4,"title":"Run only separately confirmed optional module"},{"id":5,"title":"Authenticated desktop: setup-k3s.sh --check (read-only)"},{"id":6,"title":"Approved desktop: setup-k3s.sh --apply with same reviewed flags"},{"id":7,"title":"Explicit-context server dry-run then boundary.json apply"},{"id":8,"title":"Run approved explicit-context bounded smoke; keep evidence private"},{"id":9,"title":"Inspect private journal / ownership / original flags; preserve state"},{"id":10,"title":"Explicitly start exact reviewed inactive k3s service"},{"id":11,"title":"Reviewed uninstall with exact K3S_DATA_DIR; destructive"}],"reasons":[{"id":0,"title":"Allowed by finite control; supplied facts remain external"},{"id":1,"title":"Event is not permitted in this phase"},{"id":2,"title":"Required external observation missing"},{"id":3,"title":"Selected setup action lacks explicit approval"},{"id":4,"title":"Separate explicit K3s opt-in and approval required"},{"id":5,"title":"Supported native desktop host gate failed"},{"id":6,"title":"Native desktop / explicit admin authentication required"},{"id":7,"title":"Root/kubelet/data storage gate failed; no deletion approved"},{"id":8,"title":"Private IP / routes / ports / tailnet review missing"},{"id":9,"title":"Supported explicit firewall policy not verified"},{"id":10,"title":"Ownership / drift / foreign state requires manual review"},{"id":11,"title":"Full read-only preflight did not pass"},{"id":12,"title":"Managed service / private API not ready; preserve ownership"},{"id":13,"title":"Job Complete alone is insufficient: every-Pod container results, live limits and retained runtime/quota/network evidence required"},{"id":14,"title":"Matching live TTL and Job/dependent Pod cleanup unobserved"},{"id":15,"title":"Selected module failed; inspect result, no automatic retry"},{"id":16,"title":"Recommended completion requires externally observed complete status"},{"id":17,"title":"Explicit apply approval and all current preflight gates required"},{"id":18,"title":"Boundary apply requires explicit approval/admin/context"},{"id":19,"title":"Smoke requires approval/admin/explicit context/quiet namespace"},{"id":20,"title":"Private review requires explicit approval/admin"},{"id":21,"title":"Start requires exact owned inactive service, host admin and completed owner review"},{"id":22,"title":"Destructive rollback requires admin, explicit teardown approval and backup/workload/impact review"},{"id":23,"title":"Unknown event ID"}],"sources":[{"path":"AGENTS.md","kind":"harness contract"},{"path":"README.md","kind":"entry guide"},{"path":"docs/SETUP.md","kind":"onboarding guide"},{"path":"scripts/onboard","kind":"executable control"},{"path":"scripts/lib/onboard-common.sh","kind":"module bookkeeping"},{"path":"docs/k3s/ONBOARDING.md","kind":"K3s operator specification"},{"path":"scripts/setup-k3s.sh","kind":"bootstrap safety gates"},{"path":"config/k3s/config.yaml","kind":"desired server configuration"},{"path":"config/k3s/manifests/boundary.json","kind":"desired namespace boundary"},{"path":"config/k3s/manifests/cpu-example-job.json","kind":"desired bounded CPU fixture"},{"path":"scripts/smoke-k3s.sh","kind":"runtime acceptance producer"}],"provenance":{"hapslandRepository":"https://github.com/dearlordylord/hapsland","hapslandCommit":"a0773f79ffa4babdba219c773832fa3a61cc803c","adaptation":"Independently authored .files policy, metadata, adapter and producer, borrowing only the Bend → checked adapter → projection → interactive SVG architecture described in Hapsland agent-flow-bend / agent-flow-projection / agent-flow-viz. No upstream source copied or distributed; no upstream license was exposed in the reference checkout. No review-product states, hooks, credentials or classifier calls. Hapsland pins Bend 2.0.36; this producer separately pins 2.0.37 and does not validate Hapsland artifacts."}};
export const bendSourceSha256 = "a4319a3f801c1d3b486dc3d67cc4207d5a19317ad36a61919c22b31dbe7f038c";
export const bendModelSha256 = "8070101c1dfb1ae4623e3915b14d1818c0e31c88b6d51f077f0a485c5b14c9a4";
