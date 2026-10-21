// Generated from Runtime.bend (+ WorkItem.bend, WorkerSupervision.bend) by bend 2.0.34; do not hand-edit.
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

function nat_host(n) {
  const int = typeof n === "bigint" || Number.isInteger(n);
  if (int && n >= 0 && n <= 2 ** 53) {
    return Number(n);
  }
  return { [Symbol.toPrimitive]() { throw "bend: a Nat past the largest immediate 2^48-1"; } };
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
  const re = /^\s*[+-]?((\d+\.?\d*|\.\d+)(e[+-]?\d+)?|inf(inity)?|nan)$/i;
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
  return {$: "$JMP", f: f.j?.f === f ? f.j : f, x: [x]};
}

function run_clo(j) {
  const f = (x) => run_loop(j(x));
  f.j = j;
  j.f = f;
  return f;
}

function run_loop(r) {
  while (r !== null && typeof r === "object" && r.$ === "$JMP") {
    r = r.f(...r.x);
  }
  return r;
}

function run_lib(f, n) {
  return (...a) => a.length < n ? run_lib((...b) => f(...a, ...b), n - a.length)
    : f(...a);
}

// Effect
// ======

const $0eff = Object.create(null);

function io_eff(k, run, need) {
  if (k in $0eff) {
    throw new Error("bend: two effects register " + k);
  }
  $0eff[k] = { run, need };
}
// Program
// =======

function $WorkItem$coder$(_r_0) {
  if (_r_0.$ === "WorkItem.Opus") {
    return true;
  } else if (_r_0.$ === "WorkItem.Sol") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$is_ci$(_r_0) {
  if (_r_0.$ === "WorkItem.Ci") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$is_owner$(_r_0) {
  if (_r_0.$ === "WorkItem.Owner") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$operator$(_r_0) {
  if (_r_0.$ === "WorkItem.Ci") {
    return true;
  } else if (_r_0.$ === "WorkItem.Opus") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$merger$(_r_0) {
  if (_r_0.$ === "WorkItem.Ci") {
    return true;
  } else if (_r_0.$ === "WorkItem.Owner") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$steward$(_r_0) {
  if (_r_0.$ === "WorkItem.Owner") {
    return true;
  } else if (_r_0.$ === "WorkItem.Opus") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$rid$(_a_0) {
  const _id_0 = _a_0["id"];
  return _id_0;
}

function $WorkItem$rrole$(_a_0) {
  const _role_0 = _a_0["role"];
  return _role_0;
}

function $WorkItem$same$(_a_0, _au_0) {
  return $Nat$is_eq$(($WorkItem$rid$(_a_0)), ($WorkItem$rid$(_au_0)));
}

function $WorkItem$other$(_a_0, _au_0) {
  return $Bool$not$(($Nat$is_eq$(($WorkItem$rid$(_a_0)), ($WorkItem$rid$(_au_0)))));
}

function $WorkItem$pick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $WorkItem$verify_out$(_gate_0, _good_0, _au_0, _hd_0) {
  if (_gate_0) {
    return $WorkItem$pick$(_good_0, {$: "WorkItem.DraftPR", "au": _au_0, "hd": _hd_0}, {$: "WorkItem.Implementing", "au": _au_0, "hd": _hd_0});
  } else {
    return {$: "WorkItem.Verifying", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$verify_gate$(_a_0, _au_0) {
  return $Bool$and$(($WorkItem$is_ci$(($WorkItem$rrole$(_a_0)))), ($WorkItem$other$(_a_0, _au_0)));
}

function $WorkItem$receipt_good$(_r_0, _hd_0) {
  const _sha_0 = _r_0["sha"];
  const _pass_0 = _r_0["pass"];
  return $Bool$and$(_pass_0, ($Nat$is_eq$(_sha_0, _hd_0)));
}

function $WorkItem$integrate_gate$(_a_0, _au_0) {
  return $Bool$and$(($WorkItem$operator$(($WorkItem$rrole$(_a_0)))), ($WorkItem$other$(_a_0, _au_0)));
}

function $WorkItem$accept_gate$(_a_0, _au_0) {
  return $Bool$and$(($WorkItem$is_owner$(($WorkItem$rrole$(_a_0)))), ($WorkItem$other$(_a_0, _au_0)));
}

function $WorkItem$from_proposed$(_e_0) {
  if (_e_0.$ === "WorkItem.Claim") {
    const _a_0 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$coder$(($WorkItem$rrole$(_a_0)))), {$: "WorkItem.Claimed", "au": _a_0}, {$: "WorkItem.Proposed"});
  } else if (_e_0.$ === "WorkItem.Abandon") {
    const _a_1 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$steward$(($WorkItem$rrole$(_a_1)))), {$: "WorkItem.Abandoned"}, {$: "WorkItem.Proposed"});
  } else {
    return {$: "WorkItem.Proposed"};
  }
}

function $WorkItem$from_claimed$(_au_0, _e_0) {
  if (_e_0.$ === "WorkItem.Start") {
    const _a_0 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$same$(_a_0, _au_0)), {$: "WorkItem.Implementing", "au": _au_0, "hd": 0}, {$: "WorkItem.Claimed", "au": _au_0});
  } else if (_e_0.$ === "WorkItem.Interrupt") {
    return {$: "WorkItem.Interrupted", "au": _au_0, "hd": 0};
  } else if (_e_0.$ === "WorkItem.Abandon") {
    const _a_1 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$steward$(($WorkItem$rrole$(_a_1)))), {$: "WorkItem.Abandoned"}, {$: "WorkItem.Claimed", "au": _au_0});
  } else {
    return {$: "WorkItem.Claimed", "au": _au_0};
  }
}

function $WorkItem$from_implementing$(_au_0, _hd_0, _e_0) {
  if (_e_0.$ === "WorkItem.Push") {
    const _a_0 = _e_0["a"];
    const _sha_0 = _e_0["sha"];
    return $WorkItem$pick$(($WorkItem$same$(_a_0, _au_0)), {$: "WorkItem.Implementing", "au": _au_0, "hd": _sha_0}, {$: "WorkItem.Implementing", "au": _au_0, "hd": _hd_0});
  } else if (_e_0.$ === "WorkItem.Submit") {
    const _a_1 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$same$(_a_1, _au_0)), {$: "WorkItem.Verifying", "au": _au_0, "hd": _hd_0}, {$: "WorkItem.Implementing", "au": _au_0, "hd": _hd_0});
  } else if (_e_0.$ === "WorkItem.Block") {
    return {$: "WorkItem.Blocked", "au": _au_0, "hd": _hd_0};
  } else if (_e_0.$ === "WorkItem.Interrupt") {
    return {$: "WorkItem.Interrupted", "au": _au_0, "hd": _hd_0};
  } else {
    return {$: "WorkItem.Implementing", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$from_verifying$(_au_0, _hd_0, _e_0) {
  if (_e_0.$ === "WorkItem.Verify") {
    const _a_0 = _e_0["a"];
    const _r_0 = _e_0["r"];
    return $WorkItem$verify_out$(($WorkItem$verify_gate$(_a_0, _au_0)), ($WorkItem$receipt_good$(_r_0, _hd_0)), _au_0, _hd_0);
  } else if (_e_0.$ === "WorkItem.Block") {
    return {$: "WorkItem.Blocked", "au": _au_0, "hd": _hd_0};
  } else if (_e_0.$ === "WorkItem.Interrupt") {
    return {$: "WorkItem.Interrupted", "au": _au_0, "hd": _hd_0};
  } else {
    return {$: "WorkItem.Verifying", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$integrate_out$(_gate_0, _au_0, _hd_0, _ish_0) {
  if (_gate_0) {
    return {$: "WorkItem.Integrated", "au": _au_0, "hd": _hd_0, "ig": _ish_0};
  } else {
    return {$: "WorkItem.DraftPR", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$from_draft$(_au_0, _hd_0, _e_0) {
  if (_e_0.$ === "WorkItem.Integrate") {
    const _a_0 = _e_0["a"];
    const _ish_0 = _e_0["ish"];
    const _r_0 = _e_0["r"];
    return $WorkItem$integrate_out$(($Bool$and$(($WorkItem$integrate_gate$(_a_0, _au_0)), ($WorkItem$receipt_good$(_r_0, _ish_0)))), _au_0, _hd_0, _ish_0);
  } else {
    return {$: "WorkItem.DraftPR", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$deploy_out$(_ok_0, _au_0, _hd_0, _ig_0, _served_0) {
  if (_ok_0) {
    return {$: "WorkItem.Deployed", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "dp": _served_0};
  } else {
    return {$: "WorkItem.Integrated", "au": _au_0, "hd": _hd_0, "ig": _ig_0};
  }
}

function $WorkItem$from_integrated$(_au_0, _hd_0, _ig_0, _e_0) {
  if (_e_0.$ === "WorkItem.Deploy") {
    const _a_0 = _e_0["a"];
    const _served_0 = _e_0["served"];
    return $WorkItem$deploy_out$(($Bool$and$(($WorkItem$operator$(($WorkItem$rrole$(_a_0)))), ($Nat$is_eq$(_served_0, _ig_0)))), _au_0, _hd_0, _ig_0, _served_0);
  } else {
    return {$: "WorkItem.Integrated", "au": _au_0, "hd": _hd_0, "ig": _ig_0};
  }
}

function $WorkItem$observe_out$(_ok_0, _au_0, _hd_0, _ig_0, _dp_0) {
  if (_ok_0) {
    return {$: "WorkItem.Deployed", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "dp": _dp_0};
  } else {
    return {$: "WorkItem.Integrated", "au": _au_0, "hd": _hd_0, "ig": _ig_0};
  }
}

function $WorkItem$accept_out$(_ok_0, _au_0, _hd_0, _ig_0, _dp_0, _a_0) {
  if (_ok_0) {
    return {$: "WorkItem.Accepted", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "ap": _a_0};
  } else {
    return {$: "WorkItem.Deployed", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "dp": _dp_0};
  }
}

function $WorkItem$from_deployed$(_au_0, _hd_0, _ig_0, _dp_0, _e_0) {
  if (_e_0.$ === "WorkItem.Observe") {
    const _served_0 = _e_0["served"];
    return $WorkItem$observe_out$(($Nat$is_eq$(_served_0, _ig_0)), _au_0, _hd_0, _ig_0, _dp_0);
  } else if (_e_0.$ === "WorkItem.Accept") {
    const _a_0 = _e_0["a"];
    return $WorkItem$accept_out$(($WorkItem$accept_gate$(_a_0, _au_0)), _au_0, _hd_0, _ig_0, _dp_0, _a_0);
  } else {
    return {$: "WorkItem.Deployed", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "dp": _dp_0};
  }
}

function $WorkItem$from_accepted$(_au_0, _hd_0, _ig_0, _ap_0, _e_0) {
  if (_e_0.$ === "WorkItem.Merge") {
    const _a_0 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$merger$(($WorkItem$rrole$(_a_0)))), {$: "WorkItem.Merged", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "ap": _ap_0}, {$: "WorkItem.Accepted", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "ap": _ap_0});
  } else {
    return {$: "WorkItem.Accepted", "au": _au_0, "hd": _hd_0, "ig": _ig_0, "ap": _ap_0};
  }
}

function $WorkItem$from_blocked$(_au_0, _hd_0, _e_0) {
  if (_e_0.$ === "WorkItem.Unblock") {
    const _a_0 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$steward$(($WorkItem$rrole$(_a_0)))), {$: "WorkItem.Implementing", "au": _au_0, "hd": _hd_0}, {$: "WorkItem.Blocked", "au": _au_0, "hd": _hd_0});
  } else if (_e_0.$ === "WorkItem.Abandon") {
    const _a_1 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$steward$(($WorkItem$rrole$(_a_1)))), {$: "WorkItem.Abandoned"}, {$: "WorkItem.Blocked", "au": _au_0, "hd": _hd_0});
  } else {
    return {$: "WorkItem.Blocked", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$from_interrupted$(_au_0, _hd_0, _e_0) {
  if (_e_0.$ === "WorkItem.Resume") {
    const _a_0 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$coder$(($WorkItem$rrole$(_a_0)))), {$: "WorkItem.Implementing", "au": _a_0, "hd": _hd_0}, {$: "WorkItem.Interrupted", "au": _au_0, "hd": _hd_0});
  } else if (_e_0.$ === "WorkItem.Abandon") {
    const _a_1 = _e_0["a"];
    return $WorkItem$pick$(($WorkItem$steward$(($WorkItem$rrole$(_a_1)))), {$: "WorkItem.Abandoned"}, {$: "WorkItem.Interrupted", "au": _au_0, "hd": _hd_0});
  } else {
    return {$: "WorkItem.Interrupted", "au": _au_0, "hd": _hd_0};
  }
}

function $WorkItem$step$(_s_0, _e_0) {
  if (_s_0.$ === "WorkItem.Proposed") {
    return $WorkItem$from_proposed$(_e_0);
  } else if (_s_0.$ === "WorkItem.Claimed") {
    const _au_0 = _s_0["au"];
    return $WorkItem$from_claimed$(_au_0, _e_0);
  } else if (_s_0.$ === "WorkItem.Implementing") {
    const _au_1 = _s_0["au"];
    const _hd_0 = _s_0["hd"];
    return $WorkItem$from_implementing$(_au_1, _hd_0, _e_0);
  } else if (_s_0.$ === "WorkItem.Verifying") {
    const _au_2 = _s_0["au"];
    const _hd_1 = _s_0["hd"];
    return $WorkItem$from_verifying$(_au_2, _hd_1, _e_0);
  } else if (_s_0.$ === "WorkItem.DraftPR") {
    const _au_3 = _s_0["au"];
    const _hd_2 = _s_0["hd"];
    return $WorkItem$from_draft$(_au_3, _hd_2, _e_0);
  } else if (_s_0.$ === "WorkItem.Integrated") {
    const _au_4 = _s_0["au"];
    const _hd_3 = _s_0["hd"];
    const _ig_0 = _s_0["ig"];
    return $WorkItem$from_integrated$(_au_4, _hd_3, _ig_0, _e_0);
  } else if (_s_0.$ === "WorkItem.Deployed") {
    const _au_5 = _s_0["au"];
    const _hd_4 = _s_0["hd"];
    const _ig_1 = _s_0["ig"];
    const _dp_0 = _s_0["dp"];
    return $WorkItem$from_deployed$(_au_5, _hd_4, _ig_1, _dp_0, _e_0);
  } else if (_s_0.$ === "WorkItem.Accepted") {
    const _au_6 = _s_0["au"];
    const _hd_5 = _s_0["hd"];
    const _ig_2 = _s_0["ig"];
    const _ap_0 = _s_0["ap"];
    return $WorkItem$from_accepted$(_au_6, _hd_5, _ig_2, _ap_0, _e_0);
  } else if (_s_0.$ === "WorkItem.Merged") {
    const _au_7 = _s_0["au"];
    const _hd_6 = _s_0["hd"];
    const _ig_3 = _s_0["ig"];
    const _ap_1 = _s_0["ap"];
    return {$: "WorkItem.Merged", "au": _au_7, "hd": _hd_6, "ig": _ig_3, "ap": _ap_1};
  } else if (_s_0.$ === "WorkItem.Blocked") {
    const _au_8 = _s_0["au"];
    const _hd_7 = _s_0["hd"];
    return $WorkItem$from_blocked$(_au_8, _hd_7, _e_0);
  } else if (_s_0.$ === "WorkItem.Interrupted") {
    const _au_9 = _s_0["au"];
    const _hd_8 = _s_0["hd"];
    return $WorkItem$from_interrupted$(_au_9, _hd_8, _e_0);
  } else {
    return {$: "WorkItem.Abandoned"};
  }
}

function $WorkItem$run$($0, $1) {
  for (;;) {
    {
      const _es_0 = $0;
      const _s_0 = $1;
      if (_es_0.$ === "Nil") {
        return _s_0;
      } else {
        const _e_0 = _es_0["head"];
        const _t_0 = _es_0["tail"];
        $0 = _t_0;
        $1 = ($WorkItem$step$(_s_0, _e_0));
        continue;
      }
    }
  }
}

function $WorkItem$is_off$(_av_0) {
  if (_av_0.$ === "WorkItem.Off") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$owner_event$(_e_0) {
  if (_e_0.$ === "WorkItem.Claim") {
    const _a_0 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_0)));
  } else if (_e_0.$ === "WorkItem.Start") {
    const _a_1 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_1)));
  } else if (_e_0.$ === "WorkItem.Push") {
    const _a_2 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_2)));
  } else if (_e_0.$ === "WorkItem.Submit") {
    const _a_3 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_3)));
  } else if (_e_0.$ === "WorkItem.Verify") {
    const _a_4 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_4)));
  } else if (_e_0.$ === "WorkItem.Integrate") {
    const _a_5 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_5)));
  } else if (_e_0.$ === "WorkItem.Deploy") {
    const _a_6 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_6)));
  } else if (_e_0.$ === "WorkItem.Observe") {
    return false;
  } else if (_e_0.$ === "WorkItem.Accept") {
    const _a_7 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_7)));
  } else if (_e_0.$ === "WorkItem.Merge") {
    const _a_8 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_8)));
  } else if (_e_0.$ === "WorkItem.Block") {
    const _a_9 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_9)));
  } else if (_e_0.$ === "WorkItem.Unblock") {
    const _a_10 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_10)));
  } else if (_e_0.$ === "WorkItem.Interrupt") {
    return false;
  } else if (_e_0.$ === "WorkItem.Resume") {
    const _a_11 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_11)));
  } else {
    const _a_12 = _e_0["a"];
    return $WorkItem$is_owner$(($WorkItem$rrole$(_a_12)));
  }
}

function $WorkItem$needs_kevin$(_s_0) {
  if (_s_0.$ === "WorkItem.Deployed") {
    return true;
  } else {
    return false;
  }
}

function $WorkItem$astep$go$(_hold_0, _s_0, _e_0) {
  if (_hold_0) {
    return _s_0;
  } else {
    return $WorkItem$step$(_s_0, _e_0);
  }
}

function $WorkItem$astep$(_av_0, _s_0, _e_0) {
  return $WorkItem$astep$go$(($Bool$and$(($WorkItem$is_off$(_av_0)), ($WorkItem$owner_event$(_e_0)))), _s_0, _e_0);
}

function $WorkItem$board_step$(_xs_0, _i_0, _av_0, _e_0) {
  if (_xs_0.$ === "Nil") {
    return {$: "Nil"};
  } else {
    const _x_0 = _xs_0["head"];
    const _t_0 = _xs_0["tail"];
    if (_i_0 === 0) {
      return {$: "Con", "head": ($WorkItem$astep$(_av_0, _x_0, _e_0)), "tail": _t_0};
    } else {
      const _k_0 = (_i_0 - 1);
      return {$: "Con", "head": _x_0, "tail": ($WorkItem$board_step$(_t_0, _k_0, _av_0, _e_0))};
    }
  }
}

function $WorkItem$nth$($0, $1) {
  for (;;) {
    {
      const _xs_0 = $0;
      const _i_0 = $1;
      if (_xs_0.$ === "Nil") {
        return {$: "WorkItem.Abandoned"};
      } else {
        const _x_0 = _xs_0["head"];
        const _t_0 = _xs_0["tail"];
        if (_i_0 === 0) {
          return _x_0;
        } else {
          const _k_0 = (_i_0 - 1);
          $0 = _t_0;
          $1 = _k_0;
          continue;
        }
      }
    }
  }
}

function $WorkerSupervision$pick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $WorkerSupervision$heavy$(_l_0) {
  if (_l_0.$ === "WorkerSupervision.Heavy") {
    return true;
  } else {
    return false;
  }
}

function $WorkerSupervision$declared$(_x_0) {
  if (_x_0.$ === "WorkerSupervision.NoExc") {
    return false;
  } else {
    return true;
  }
}

function $WorkerSupervision$on_groot$(_h_0) {
  if (_h_0.$ === "WorkerSupervision.Groot") {
    return true;
  } else {
    return false;
  }
}

function $WorkerSupervision$wload$(_w_0) {
  const _load_0 = _w_0["load"];
  return _load_0;
}

function $WorkerSupervision$wexc$(_w_0) {
  const _exc_0 = _w_0["exc"];
  return _exc_0;
}

function $WorkerSupervision$placed$(_w_0, _h_0) {
  const _x_0 = ($Bool$not$(($WorkerSupervision$heavy$(($WorkerSupervision$wload$(_w_0))))));
  const _x_1 = ($WorkerSupervision$declared$(($WorkerSupervision$wexc$(_w_0))));
  const _x_2 = ($Bool$not$(($WorkerSupervision$on_groot$(_h_0))));
  const _x_3 = (_x_0 || _x_1);
  return (_x_2 || _x_3);
}

function $WorkerSupervision$dec$(_n_0) {
  if (_n_0 === 0) {
    return 0;
  } else {
    const _k_0 = (_n_0 - 1);
    return _k_0;
  }
}

function $WorkerSupervision$is_zero$(_n_0) {
  if (_n_0 === 0) {
    return true;
  } else {
    return false;
  }
}

function $WorkerSupervision$late$(_now_0, _base_0, _lim_0) {
  return $Nat$is_gt$(_now_0, nat_chk(_base_0 + _lim_0));
}

function $WorkerSupervision$from_dispatched$(_w_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Start") {
    const _h_0 = _e_0["h"];
    const _t_0 = _e_0["t"];
    return $WorkerSupervision$pick$(($WorkerSupervision$placed$(_w_0, _h_0)), {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _t_0, "bg": 0}, {$: "WorkerSupervision.Dispatched", "w": _w_0});
  } else if (_e_0.$ === "WorkerSupervision.Interrupt") {
    const _t_1 = _e_0["t"];
    return {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _t_1, "bg": 0};
  } else if (_e_0.$ === "WorkerSupervision.Abandon") {
    return {$: "WorkerSupervision.Abandoned", "w": _w_0};
  } else {
    return {$: "WorkerSupervision.Dispatched", "w": _w_0};
  }
}

function $WorkerSupervision$from_running$(_w_0, _h_0, _hb_0, _bg_0, _e_0, _lim_0) {
  if (_e_0.$ === "WorkerSupervision.Beat") {
    const _t_0 = _e_0["t"];
    return {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _t_0, "bg": _bg_0};
  } else if (_e_0.$ === "WorkerSupervision.Spawn") {
    return {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": nat_chk(_bg_0 + 1)};
  } else if (_e_0.$ === "WorkerSupervision.Reap") {
    return {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": ($WorkerSupervision$dec$(_bg_0))};
  } else if (_e_0.$ === "WorkerSupervision.Tick") {
    const _now_0 = _e_0["now"];
    return $WorkerSupervision$pick$(($WorkerSupervision$late$(_now_0, _hb_0, _lim_0)), {$: "WorkerSupervision.Stalled", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": _bg_0}, {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Finish") {
    return {$: "WorkerSupervision.Completed", "w": _w_0, "bg": _bg_0};
  } else if (_e_0.$ === "WorkerSupervision.Interrupt") {
    const _t_1 = _e_0["t"];
    return {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _t_1, "bg": _bg_0};
  } else {
    return {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": _bg_0};
  }
}

function $WorkerSupervision$from_stalled$(_w_0, _h_0, _hb_0, _bg_0, _e_0, _lim_0) {
  if (_e_0.$ === "WorkerSupervision.Beat") {
    const _t_0 = _e_0["t"];
    return {$: "WorkerSupervision.Running", "w": _w_0, "h": _h_0, "hb": _t_0, "bg": _bg_0};
  } else if (_e_0.$ === "WorkerSupervision.Reap") {
    return {$: "WorkerSupervision.Stalled", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": ($WorkerSupervision$dec$(_bg_0))};
  } else if (_e_0.$ === "WorkerSupervision.Tick") {
    const _now_0 = _e_0["now"];
    return $WorkerSupervision$pick$(($WorkerSupervision$late$(_now_0, _hb_0, nat_chk(_lim_0 + _lim_0))), {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _now_0, "bg": _bg_0}, {$: "WorkerSupervision.Stalled", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Finish") {
    return {$: "WorkerSupervision.Completed", "w": _w_0, "bg": _bg_0};
  } else if (_e_0.$ === "WorkerSupervision.Interrupt") {
    const _t_1 = _e_0["t"];
    return {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _t_1, "bg": _bg_0};
  } else {
    return {$: "WorkerSupervision.Stalled", "w": _w_0, "h": _h_0, "hb": _hb_0, "bg": _bg_0};
  }
}

function $WorkerSupervision$from_interrupted$(_w_0, _at_0, _bg_0, _e_0, _lim_0) {
  if (_e_0.$ === "WorkerSupervision.Reap") {
    return {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _at_0, "bg": ($WorkerSupervision$dec$(_bg_0))};
  } else if (_e_0.$ === "WorkerSupervision.Tick") {
    const _now_0 = _e_0["now"];
    return $WorkerSupervision$pick$(($WorkerSupervision$late$(_now_0, _at_0, _lim_0)), {$: "WorkerSupervision.Overdue", "w": _w_0, "at": _at_0, "bg": _bg_0}, {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _at_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Resume") {
    const _by_0 = _e_0["by"];
    const _log_0 = _e_0["log"];
    return $WorkerSupervision$pick$(_log_0, {$: "WorkerSupervision.Resumed", "w": _w_0, "by": _by_0, "bg": _bg_0}, {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _at_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Abandon") {
    return $WorkerSupervision$pick$(($WorkerSupervision$is_zero$(_bg_0)), {$: "WorkerSupervision.Abandoned", "w": _w_0}, {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _at_0, "bg": _bg_0});
  } else {
    return {$: "WorkerSupervision.Interrupted", "w": _w_0, "at": _at_0, "bg": _bg_0};
  }
}

function $WorkerSupervision$from_overdue$(_w_0, _at_0, _bg_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Reap") {
    return {$: "WorkerSupervision.Overdue", "w": _w_0, "at": _at_0, "bg": ($WorkerSupervision$dec$(_bg_0))};
  } else if (_e_0.$ === "WorkerSupervision.Resume") {
    const _by_0 = _e_0["by"];
    const _log_0 = _e_0["log"];
    return $WorkerSupervision$pick$(_log_0, {$: "WorkerSupervision.Resumed", "w": _w_0, "by": _by_0, "bg": _bg_0}, {$: "WorkerSupervision.Overdue", "w": _w_0, "at": _at_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Abandon") {
    return $WorkerSupervision$pick$(($WorkerSupervision$is_zero$(_bg_0)), {$: "WorkerSupervision.Abandoned", "w": _w_0}, {$: "WorkerSupervision.Overdue", "w": _w_0, "at": _at_0, "bg": _bg_0});
  } else {
    return {$: "WorkerSupervision.Overdue", "w": _w_0, "at": _at_0, "bg": _bg_0};
  }
}

function $WorkerSupervision$from_completed$(_w_0, _bg_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Reap") {
    return {$: "WorkerSupervision.Completed", "w": _w_0, "bg": ($WorkerSupervision$dec$(_bg_0))};
  } else if (_e_0.$ === "WorkerSupervision.Integrate") {
    return $WorkerSupervision$pick$(($WorkerSupervision$is_zero$(_bg_0)), {$: "WorkerSupervision.Integrated", "w": _w_0}, {$: "WorkerSupervision.Completed", "w": _w_0, "bg": _bg_0});
  } else if (_e_0.$ === "WorkerSupervision.Abandon") {
    return $WorkerSupervision$pick$(($WorkerSupervision$is_zero$(_bg_0)), {$: "WorkerSupervision.Abandoned", "w": _w_0}, {$: "WorkerSupervision.Completed", "w": _w_0, "bg": _bg_0});
  } else {
    return {$: "WorkerSupervision.Completed", "w": _w_0, "bg": _bg_0};
  }
}

function $WorkerSupervision$step$(_s_0, _e_0, _lim_0) {
  if (_s_0.$ === "WorkerSupervision.Dispatched") {
    const _w_0 = _s_0["w"];
    return $WorkerSupervision$from_dispatched$(_w_0, _e_0);
  } else if (_s_0.$ === "WorkerSupervision.Running") {
    const _w_1 = _s_0["w"];
    const _h_0 = _s_0["h"];
    const _hb_0 = _s_0["hb"];
    const _bg_0 = _s_0["bg"];
    return $WorkerSupervision$from_running$(_w_1, _h_0, _hb_0, _bg_0, _e_0, _lim_0);
  } else if (_s_0.$ === "WorkerSupervision.Stalled") {
    const _w_2 = _s_0["w"];
    const _h_1 = _s_0["h"];
    const _hb_1 = _s_0["hb"];
    const _bg_1 = _s_0["bg"];
    return $WorkerSupervision$from_stalled$(_w_2, _h_1, _hb_1, _bg_1, _e_0, _lim_0);
  } else if (_s_0.$ === "WorkerSupervision.Interrupted") {
    const _w_3 = _s_0["w"];
    const _at_0 = _s_0["at"];
    const _bg_2 = _s_0["bg"];
    return $WorkerSupervision$from_interrupted$(_w_3, _at_0, _bg_2, _e_0, _lim_0);
  } else if (_s_0.$ === "WorkerSupervision.Overdue") {
    const _w_4 = _s_0["w"];
    const _at_1 = _s_0["at"];
    const _bg_3 = _s_0["bg"];
    return $WorkerSupervision$from_overdue$(_w_4, _at_1, _bg_3, _e_0);
  } else if (_s_0.$ === "WorkerSupervision.Completed") {
    const _w_5 = _s_0["w"];
    const _bg_4 = _s_0["bg"];
    return $WorkerSupervision$from_completed$(_w_5, _bg_4, _e_0);
  } else if (_s_0.$ === "WorkerSupervision.Resumed") {
    const _w_6 = _s_0["w"];
    const _by_0 = _s_0["by"];
    const _bg_5 = _s_0["bg"];
    return {$: "WorkerSupervision.Resumed", "w": _w_6, "by": _by_0, "bg": _bg_5};
  } else if (_s_0.$ === "WorkerSupervision.Abandoned") {
    const _w_7 = _s_0["w"];
    return {$: "WorkerSupervision.Abandoned", "w": _w_7};
  } else {
    const _w_8 = _s_0["w"];
    return {$: "WorkerSupervision.Integrated", "w": _w_8};
  }
}

function $WorkerSupervision$run$($0, $1, $2) {
  for (;;) {
    {
      const _es_0 = $0;
      const _lim_0 = $1;
      const _s_0 = $2;
      if (_es_0.$ === "Nil") {
        return _s_0;
      } else {
        const _e_0 = _es_0["head"];
        const _t_0 = _es_0["tail"];
        $0 = _t_0;
        $1 = _lim_0;
        $2 = ($WorkerSupervision$step$(_s_0, _e_0, _lim_0));
        continue;
      }
    }
  }
}

function $WorkerSupervision$needs_kevin$(_s_0) {
  if (_s_0.$ === "WorkerSupervision.Overdue") {
    return true;
  } else {
    return false;
  }
}

function $WorkerSupervision$lpick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $WorkerSupervision$lfree$(_e_0) {
  if (_e_0.$ === "WorkerSupervision.Acquire") {
    const _a_0 = _e_0["a"];
    return {$: "WorkerSupervision.Held", "o": _a_0};
  } else {
    return {$: "WorkerSupervision.Free"};
  }
}

function $WorkerSupervision$lheld$(_o_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Acquire") {
    return {$: "WorkerSupervision.Held", "o": _o_0};
  } else if (_e_0.$ === "WorkerSupervision.Release") {
    const _a_1 = _e_0["a"];
    return $WorkerSupervision$lpick$(($Nat$is_eq$(_a_1, _o_0)), {$: "WorkerSupervision.Free"}, {$: "WorkerSupervision.Held", "o": _o_0});
  } else {
    const _a_2 = _e_0["a"];
    const _dead_0 = _e_0["dead"];
    return $WorkerSupervision$lpick$(_dead_0, {$: "WorkerSupervision.Held", "o": _a_2}, {$: "WorkerSupervision.Held", "o": _o_0});
  }
}

function $WorkerSupervision$lstep$(_l_0, _e_0) {
  if (_l_0.$ === "WorkerSupervision.Free") {
    return $WorkerSupervision$lfree$(_e_0);
  } else {
    const _o_0 = _l_0["o"];
    return $WorkerSupervision$lheld$(_o_0, _e_0);
  }
}

function $WorkerSupervision$holds$(_l_0, _a_0) {
  if (_l_0.$ === "WorkerSupervision.Free") {
    return false;
  } else {
    const _o_0 = _l_0["o"];
    return $Nat$is_eq$(_o_0, _a_0);
  }
}

function $WorkerSupervision$epick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $WorkerSupervision$fg_is$(_f_0, _app_0) {
  if (_f_0.$ === "WorkerSupervision.Unknown") {
    return false;
  } else {
    const _x_0 = _f_0["app"];
    return $Nat$is_eq$(_x_0, _app_0);
  }
}

function $WorkerSupervision$dev_eff$(_lk_0, _fg_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Install") {
    const _a_0 = _e_0["a"];
    return $WorkerSupervision$epick$(($WorkerSupervision$holds$(_lk_0, _a_0)), {$: "WorkerSupervision.Installed", "a": _a_0}, {$: "WorkerSupervision.NoEff"});
  } else if (_e_0.$ === "WorkerSupervision.Input") {
    const _a_1 = _e_0["a"];
    const _app_0 = _e_0["app"];
    return $WorkerSupervision$epick$(($WorkerSupervision$fg_is$(_fg_0, _app_0)), {$: "WorkerSupervision.Typed", "a": _a_1, "app": _app_0}, {$: "WorkerSupervision.NoEff"});
  } else {
    return {$: "WorkerSupervision.NoEff"};
  }
}

function $WorkerSupervision$peff$(_p_0, _e_0) {
  const _lk_0 = _p_0["lk"];
  const _fg_0 = _p_0["fg"];
  return $WorkerSupervision$dev_eff$(_lk_0, _fg_0, _e_0);
}

function $WorkerSupervision$dev_step$(_lk_0, _fg_0, _e_0) {
  if (_e_0.$ === "WorkerSupervision.Lock") {
    const _a_0 = _e_0["a"];
    return {$: "WorkerSupervision.Dev", "lk": ($WorkerSupervision$lstep$(_lk_0, {$: "WorkerSupervision.Acquire", "a": _a_0})), "fg": _fg_0};
  } else if (_e_0.$ === "WorkerSupervision.Unlock") {
    const _a_1 = _e_0["a"];
    return {$: "WorkerSupervision.Dev", "lk": ($WorkerSupervision$lstep$(_lk_0, {$: "WorkerSupervision.Release", "a": _a_1})), "fg": _fg_0};
  } else if (_e_0.$ === "WorkerSupervision.Peek") {
    const _app_0 = _e_0["app"];
    return {$: "WorkerSupervision.Dev", "lk": _lk_0, "fg": {$: "WorkerSupervision.Seen", "app": _app_0}};
  } else if (_e_0.$ === "WorkerSupervision.Install") {
    return {$: "WorkerSupervision.Dev", "lk": _lk_0, "fg": _fg_0};
  } else {
    return {$: "WorkerSupervision.Dev", "lk": _lk_0, "fg": {$: "WorkerSupervision.Unknown"}};
  }
}

function $WorkerSupervision$pstep$(_p_0, _e_0) {
  const _lk_0 = _p_0["lk"];
  const _fg_0 = _p_0["fg"];
  return $WorkerSupervision$dev_step$(_lk_0, _fg_0, _e_0);
}

function $IntegrationOwner$pick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $IntegrationOwner$advance$(_s_0, _e_0) {
  if (_s_0.$ === "IntegrationOwner.Branch") {
    if (_e_0.$ === "IntegrationOwner.Draft") {
      return {$: "IntegrationOwner.DraftPR"};
    } else {
      return {$: "IntegrationOwner.Branch"};
    }
  } else if (_s_0.$ === "IntegrationOwner.DraftPR") {
    if (_e_0.$ === "IntegrationOwner.Queue") {
      return {$: "IntegrationOwner.Queued"};
    } else {
      return {$: "IntegrationOwner.DraftPR"};
    }
  } else if (_s_0.$ === "IntegrationOwner.Queued") {
    if (_e_0.$ === "IntegrationOwner.Integrate") {
      const _lease_0 = _e_0["lease"];
      const _stack_0 = _e_0["stack"];
      const _independent_0 = _e_0["independent"];
      return $IntegrationOwner$pick$(($Bool$and$(_lease_0, ($Bool$and$(_stack_0, _independent_0)))), {$: "IntegrationOwner.OnIntegrationBranch"}, {$: "IntegrationOwner.Queued"});
    } else {
      return {$: "IntegrationOwner.Queued"};
    }
  } else if (_s_0.$ === "IntegrationOwner.OnIntegrationBranch") {
    if (_e_0.$ === "IntegrationOwner.Deploy") {
      const _equal_0 = _e_0["equal"];
      return $IntegrationOwner$pick$(_equal_0, {$: "IntegrationOwner.Deployed"}, {$: "IntegrationOwner.OnIntegrationBranch"});
    } else {
      return {$: "IntegrationOwner.OnIntegrationBranch"};
    }
  } else if (_s_0.$ === "IntegrationOwner.Deployed") {
    if (_e_0.$ === "IntegrationOwner.Accept") {
      const _owner_0 = _e_0["owner"];
      return $IntegrationOwner$pick$(_owner_0, {$: "IntegrationOwner.OwnerAccepted"}, {$: "IntegrationOwner.Deployed"});
    } else {
      return {$: "IntegrationOwner.Deployed"};
    }
  } else if (_s_0.$ === "IntegrationOwner.OwnerAccepted") {
    if (_e_0.$ === "IntegrationOwner.Merge") {
      return {$: "IntegrationOwner.Merged"};
    } else {
      return {$: "IntegrationOwner.OwnerAccepted"};
    }
  } else if (_s_0.$ === "IntegrationOwner.Parked") {
    if (_e_0.$ === "IntegrationOwner.Resume") {
      return {$: "IntegrationOwner.Queued"};
    } else if (_e_0.$ === "IntegrationOwner.Expire") {
      const _expired_0 = _e_0["expired"];
      return $IntegrationOwner$pick$(_expired_0, {$: "IntegrationOwner.Queued"}, {$: "IntegrationOwner.Parked"});
    } else {
      return {$: "IntegrationOwner.Parked"};
    }
  } else if (_s_0.$ === "IntegrationOwner.Conflicted") {
    if (_e_0.$ === "IntegrationOwner.Resume") {
      return {$: "IntegrationOwner.Queued"};
    } else {
      return {$: "IntegrationOwner.Conflicted"};
    }
  } else {
    return _s_0;
  }
}

function $IntegrationOwner$observe$(_s_0, _equal_0) {
  if (_s_0.$ === "IntegrationOwner.Deployed") {
    return $IntegrationOwner$pick$(_equal_0, {$: "IntegrationOwner.Deployed"}, {$: "IntegrationOwner.OnIntegrationBranch"});
  } else if (_s_0.$ === "IntegrationOwner.OwnerAccepted") {
    return $IntegrationOwner$pick$(_equal_0, {$: "IntegrationOwner.OwnerAccepted"}, {$: "IntegrationOwner.OnIntegrationBranch"});
  } else {
    return _s_0;
  }
}

function $IntegrationOwner$active$(_s_0, _e_0) {
  if (_e_0.$ === "IntegrationOwner.Park") {
    const _reason_0 = _e_0["reason"];
    const _future_0 = _e_0["future"];
    return $IntegrationOwner$pick$(($Bool$and$(_reason_0, _future_0)), {$: "IntegrationOwner.Parked"}, _s_0);
  } else if (_e_0.$ === "IntegrationOwner.Conflict") {
    return {$: "IntegrationOwner.Conflicted"};
  } else if (_e_0.$ === "IntegrationOwner.Observe") {
    const _equal_0 = _e_0["equal"];
    return $IntegrationOwner$observe$(_s_0, _equal_0);
  } else {
    return $IntegrationOwner$advance$(_s_0, _e_0);
  }
}

function $IntegrationOwner$step$(_s_0, _e_0) {
  if (_s_0.$ === "IntegrationOwner.Merged") {
    return {$: "IntegrationOwner.Merged"};
  } else {
    return $IntegrationOwner$active$(_s_0, _e_0);
  }
}

function $IntegrationOwner$overdue$(_age_0, _contained_0, _parked_0) {
  return $Bool$and$(($Bool$not$((_contained_0 || _parked_0))), ($Nat$is_ge$(_age_0, 86400)));
}

function $IntegrationOwner$lpick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $IntegrationOwner$acquire$(_l_0, _actor_0, _until_0, _now_0) {
  if (_l_0.$ === "IntegrationOwner.Free") {
    return $IntegrationOwner$lpick$(($Nat$is_gt$(_until_0, _now_0)), {$: "IntegrationOwner.Held", "owner": _actor_0, "until": _until_0}, {$: "IntegrationOwner.Free"});
  } else {
    const _owner_0 = _l_0["owner"];
    const _expiry_0 = _l_0["until"];
    return $IntegrationOwner$lpick$(($Bool$and$(($Nat$is_ge$(_now_0, _expiry_0)), ($Nat$is_gt$(_until_0, _now_0)))), {$: "IntegrationOwner.Held", "owner": _actor_0, "until": _until_0}, {$: "IntegrationOwner.Held", "owner": _owner_0, "until": _expiry_0});
  }
}

function $Ops$groot_class$(_c_0) {
  if (_c_0.$ === "Ops.CGpu") {
    return true;
  } else if (_c_0.$ === "Ops.CBend") {
    return true;
  } else if (_c_0.$ === "Ops.CLean") {
    return true;
  } else if (_c_0.$ === "Ops.CService") {
    return true;
  } else if (_c_0.$ === "Ops.CAgent") {
    return true;
  } else if (_c_0.$ === "Ops.CTiny") {
    return true;
  } else {
    return false;
  }
}

function $Ops$admits$(_l_0, _c_0) {
  if (_l_0.$ === "Ops.LGroot") {
    return $Ops$groot_class$(_c_0);
  } else {
    return true;
  }
}

function $Ops$place_phone$(_p_0) {
  if (_p_0) {
    return {$: "Ops.RunOn", "l": {$: "Ops.LPhone"}};
  } else {
    return {$: "Ops.Wait"};
  }
}

function $Ops$place_off$(_m_0, _p_0) {
  if (_m_0) {
    return {$: "Ops.RunOn", "l": {$: "Ops.LMbp"}};
  } else {
    return $Ops$place_phone$(_p_0);
  }
}

function $Ops$place_by$(_g_0, _m_0, _p_0) {
  if (_g_0) {
    return {$: "Ops.RunOn", "l": {$: "Ops.LGroot"}};
  } else {
    return $Ops$place_off$(_m_0, _p_0);
  }
}

function $Ops$place$(_c_0, _m_0, _p_0) {
  return $Ops$place_by$(($Ops$groot_class$(_c_0)), _m_0, _p_0);
}

function $Ops$runs_on_groot$(_x_0) {
  if (_x_0.$ === "Ops.RunOn") {
    const _t_0 = _x_0["l"];
    if (_t_0.$ === "Ops.LGroot") {
      return true;
    } else {
      return false;
    }
  } else {
    return false;
  }
}

function $Ops$served_allows$(_op_0, _txn_0) {
  if (_op_0.$ === "Ops.GMergeFF") {
    return _txn_0;
  } else if (_op_0.$ === "Ops.GRollback") {
    return _txn_0;
  } else {
    return false;
  }
}

function $Ops$wt_allows$(_served_0, _op_0, _txn_0) {
  if (_served_0) {
    return $Ops$served_allows$(_op_0, _txn_0);
  } else {
    return true;
  }
}

function $Ops$review_ok$(_gated_0, _receipt_0) {
  const _x_0 = ($Bool$not$(_gated_0));
  return (_x_0 || _receipt_0);
}

function $Ops$pre_ok$(_clean_0, _ff_0, _gated_0, _receipt_0) {
  return $Bool$and$(_clean_0, ($Bool$and$(_ff_0, ($Ops$review_ok$(_gated_0, _receipt_0)))));
}

function $Ops$ready$(_call_0, _idle_0) {
  return $Bool$and$(($Bool$not$(_call_0)), _idle_0);
}

function $Ops$finish$(_check_0) {
  if (_check_0) {
    return {$: "Ops.OPromoted"};
  } else {
    return {$: "Ops.ORolledBack"};
  }
}

function $Ops$go$(_r_0, _check_0) {
  if (_r_0) {
    return $Ops$finish$(_check_0);
  } else {
    return {$: "Ops.ODeferred"};
  }
}

function $Ops$decide$(_ok_0, _r_0, _check_0) {
  if (_ok_0) {
    return $Ops$go$(_r_0, _check_0);
  } else {
    return {$: "Ops.ORefused"};
  }
}

function $Ops$rollout$(_q_0, _check_0) {
  const _clean_0 = _q_0["clean"];
  const _ff_0 = _q_0["ff"];
  const _gated_0 = _q_0["gated"];
  const _receipt_0 = _q_0["receipt"];
  const _call_0 = _q_0["call"];
  const _idle_0 = _q_0["idle"];
  return $Ops$decide$(($Ops$pre_ok$(_clean_0, _ff_0, _gated_0, _receipt_0)), ($Ops$ready$(_call_0, _idle_0)), _check_0);
}

function $Ops$promoted$(_x_0) {
  if (_x_0.$ === "Ops.OPromoted") {
    return true;
  } else {
    return false;
  }
}

function $Ops$touched$(_x_0) {
  if (_x_0.$ === "Ops.OPromoted") {
    return true;
  } else if (_x_0.$ === "Ops.ORolledBack") {
    return true;
  } else {
    return false;
  }
}

function $Ops$vis_private$(_v_0) {
  if (_v_0.$ === "Ops.VPrivate") {
    return true;
  } else {
    return false;
  }
}

function $Ops$push_allows$(_private_0, _v_0) {
  if (_private_0) {
    return $Ops$vis_private$(_v_0);
  } else {
    return true;
  }
}

function $Ops$phone_allows$(_a_0, _call_0) {
  if (_a_0.$ === "Ops.PTap") {
    const _intent_0 = _a_0["intent"];
    const _fg_0 = _a_0["fg"];
    return $Bool$and$(_intent_0, _fg_0);
  } else if (_a_0.$ === "Ops.PInstall") {
    const _chain_0 = _a_0["chain"];
    return $Bool$not$(($Bool$and$(_chain_0, _call_0)));
  } else {
    const _chain_1 = _a_0["chain"];
    return $Bool$not$(($Bool$and$(_chain_1, _call_0)));
  }
}

function $Ops$mem$(_x_0, _l_0) {
  if (_l_0.$ === "Nil") {
    return false;
  } else {
    const _h_0 = _l_0["head"];
    const _t_0 = _l_0["tail"];
    const _x_1 = ($Nat$is_eq$(_h_0, _x_0));
    const _x_2 = ($Ops$mem$(_x_0, _t_0));
    return (_x_1 || _x_2);
  }
}

function $Ops$a11y_ok$(_pre_0, _post_0, _rm_0) {
  if (_pre_0.$ === "Nil") {
    return true;
  } else {
    const _h_0 = _pre_0["head"];
    const _t_0 = _pre_0["tail"];
    const _x_0 = ($Ops$mem$(_h_0, _post_0));
    const _x_1 = ($Ops$mem$(_h_0, _rm_0));
    return $Bool$and$((_x_0 || _x_1), ($Ops$a11y_ok$(_t_0, _post_0, _rm_0)));
  }
}

function $Ops$route_ok$(_cancelled_0, _sol_0, _design_0) {
  return $Bool$and$(($Bool$not$(_cancelled_0)), ($Bool$not$(($Bool$and$(_design_0, _sol_0)))));
}

function $Ops$late$(_now_0, _base_0, _lim_0) {
  return $Nat$is_gt$(_now_0, nat_chk(_base_0 + _lim_0));
}

function $Ops$npick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $Ops$from_healthy$(_e_0) {
  const _ok_0 = _e_0["ok"];
  const _now_0 = _e_0["now"];
  return $Ops$npick$(_ok_0, {$: "Ops.NHealthy"}, {$: "Ops.NBad", "since": _now_0});
}

function $Ops$from_bad$(_s_0, _e_0, _lim_0) {
  const _ok_0 = _e_0["ok"];
  const _now_0 = _e_0["now"];
  return $Ops$npick$(_ok_0, {$: "Ops.NHealthy"}, ($Ops$npick$(($Ops$late$(_now_0, _s_0, _lim_0)), {$: "Ops.NNotified", "since": _s_0}, {$: "Ops.NBad", "since": _s_0})));
}

function $Ops$from_notified$(_s_0, _e_0) {
  const _ok_0 = _e_0["ok"];
  return $Ops$npick$(_ok_0, {$: "Ops.NHealthy"}, {$: "Ops.NNotified", "since": _s_0});
}

function $Ops$nstep$(_s_0, _e_0, _lim_0) {
  if (_s_0.$ === "Ops.NHealthy") {
    return $Ops$from_healthy$(_e_0);
  } else if (_s_0.$ === "Ops.NBad") {
    const _since_0 = _s_0["since"];
    return $Ops$from_bad$(_since_0, _e_0, _lim_0);
  } else {
    const _since_1 = _s_0["since"];
    return $Ops$from_notified$(_since_1, _e_0);
  }
}

function $Ops$bad_eff$(_s_0, _e_0, _lim_0) {
  const _ok_0 = _e_0["ok"];
  const _now_0 = _e_0["now"];
  return $Bool$and$(($Bool$not$(_ok_0)), ($Ops$late$(_now_0, _s_0, _lim_0)));
}

function $Ops$neff$(_s_0, _e_0, _lim_0) {
  if (_s_0.$ === "Ops.NBad") {
    const _since_0 = _s_0["since"];
    return $Ops$bad_eff$(_since_0, _e_0, _lim_0);
  } else {
    return false;
  }
}

function $Ops$notified$(_s_0) {
  if (_s_0.$ === "Ops.NNotified") {
    return true;
  } else {
    return false;
  }
}

function $Ops$rpick$(_ok_0, _x_0, _y_0) {
  if (_ok_0) {
    return _x_0;
  } else {
    return _y_0;
  }
}

function $Ops$ract$(_g_0, _e_0) {
  if (_e_0.$ === "Ops.GwRestart") {
    const _x_0 = _e_0["gw"];
    return $Ops$rpick$(($Nat$is_eq$(_x_0, _g_0)), {$: "Ops.RInterrupted", "gw": _g_0}, {$: "Ops.RActive", "gw": _g_0});
  } else if (_e_0.$ === "Ops.RunError") {
    return {$: "Ops.RFailed"};
  } else if (_e_0.$ === "Ops.RunDone") {
    return {$: "Ops.RDone"};
  } else {
    return {$: "Ops.RActive", "gw": _g_0};
  }
}

function $Ops$rint$(_g_0, _e_0) {
  if (_e_0.$ === "Ops.ResumeRun") {
    const _session_0 = _e_0["session"];
    return $Ops$rpick$(_session_0, {$: "Ops.RResumed"}, {$: "Ops.RInterrupted", "gw": _g_0});
  } else if (_e_0.$ === "Ops.ReportRun") {
    return {$: "Ops.RReported"};
  } else {
    return {$: "Ops.RInterrupted", "gw": _g_0};
  }
}

function $Ops$rstep$(_s_0, _e_0) {
  if (_s_0.$ === "Ops.RActive") {
    const _g_0 = _s_0["gw"];
    return $Ops$ract$(_g_0, _e_0);
  } else if (_s_0.$ === "Ops.RInterrupted") {
    const _g_1 = _s_0["gw"];
    return $Ops$rint$(_g_1, _e_0);
  } else if (_s_0.$ === "Ops.RFailed") {
    return {$: "Ops.RFailed"};
  } else if (_s_0.$ === "Ops.RDone") {
    return {$: "Ops.RDone"};
  } else if (_s_0.$ === "Ops.RResumed") {
    return {$: "Ops.RResumed"};
  } else {
    return {$: "Ops.RReported"};
  }
}

function $Ops$rfailed$(_s_0) {
  if (_s_0.$ === "Ops.RFailed") {
    return true;
  } else {
    return false;
  }
}

function $OpsLayer$by_bool$(_ok_0) {
  if (_ok_0) {
    return {$: "OpsLayer.GAdmitted"};
  } else {
    return {$: "OpsLayer.GRefused"};
  }
}

function $OpsLayer$by_place$(_p_0) {
  if (_p_0.$ === "Ops.RunOn") {
    return {$: "OpsLayer.GAdmitted"};
  } else {
    return {$: "OpsLayer.GWaiting"};
  }
}

function $OpsLayer$by_out$(_o_0) {
  if (_o_0.$ === "Ops.ORefused") {
    return {$: "OpsLayer.GRefused"};
  } else if (_o_0.$ === "Ops.ODeferred") {
    return {$: "OpsLayer.GWaiting"};
  } else if (_o_0.$ === "Ops.OPromoted") {
    return {$: "OpsLayer.GAdmitted"};
  } else {
    return {$: "OpsLayer.GRolledBack"};
  }
}

function $OpsLayer$gate_step$(_s_0, _e_0) {
  if (_e_0.$ === "OpsLayer.GPlace") {
    const _c_0 = _e_0["c"];
    const _mbp_0 = _e_0["mbp"];
    const _phone_0 = _e_0["phone"];
    return $OpsLayer$by_place$(($Ops$place$(_c_0, _mbp_0, _phone_0)));
  } else if (_e_0.$ === "OpsLayer.GGit") {
    const _served_0 = _e_0["served"];
    const _op_0 = _e_0["op"];
    const _txn_0 = _e_0["txn"];
    return $OpsLayer$by_bool$(($Ops$wt_allows$(_served_0, _op_0, _txn_0)));
  } else if (_e_0.$ === "OpsLayer.GRoll") {
    const _q_0 = _e_0["q"];
    const _check_0 = _e_0["check"];
    return $OpsLayer$by_out$(($Ops$rollout$(_q_0, _check_0)));
  } else if (_e_0.$ === "OpsLayer.GPush") {
    const _private_0 = _e_0["private"];
    const _vis_0 = _e_0["vis"];
    return $OpsLayer$by_bool$(($Ops$push_allows$(_private_0, _vis_0)));
  } else if (_e_0.$ === "OpsLayer.GPhone") {
    const _a_0 = _e_0["a"];
    const _call_0 = _e_0["call"];
    return $OpsLayer$by_bool$(($Ops$phone_allows$(_a_0, _call_0)));
  } else {
    const _cancelled_0 = _e_0["cancelled"];
    const _sol_0 = _e_0["sol"];
    const _design_0 = _e_0["design"];
    return $OpsLayer$by_bool$(($Ops$route_ok$(_cancelled_0, _sol_0, _design_0)));
  }
}

function $abi_version$() {
  return 1;
}

function $Nat$is_eq$(_a_0, _b_0) {
  return $Cmp$is_eq$(cmp_new(_a_0, _b_0));
}

function $Bool$not$(_b_0) {
  if (!_b_0) {
    return true;
  } else {
    return false;
  }
}

function $Bool$and$(_a_0, _b_0) {
  if (!_a_0) {
    return false;
  } else {
    return _b_0;
  }
}

function $Nat$is_gt$(_a_0, _b_0) {
  return $Cmp$is_gt$(cmp_new(_a_0, _b_0));
}

function $Nat$is_ge$(_a_0, _b_0) {
  return $Cmp$is_ge$(cmp_new(_a_0, _b_0));
}

function $Cmp$is_eq$(_c_0) {
  if (_c_0.$ === "EQ") {
    return true;
  } else {
    return false;
  }
}

function $Cmp$is_gt$(_c_0) {
  if (_c_0.$ === "GT") {
    return true;
  } else {
    return false;
  }
}

function $Cmp$is_ge$(_c_0) {
  if (_c_0.$ === "LT") {
    return false;
  } else {
    return true;
  }
}

function $0m0(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Actor": at = at[key] = {...v, "id": nat_host(v["id"])}; return top[0];
      default: throw "bend: WorkItem.Actor has no tag " + v?.$ + " (its tags: WorkItem.Actor); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m1(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Actor": at = at[key] = {...v, "id": BigInt(v["id"])}; return top[0];
      default: throw "bend: WorkItem.Actor has no tag " + v?.$ + " (its tags: WorkItem.Actor); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m2(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Proposed": at[key] = v; return top[0];
      case "WorkItem.Claimed": at = at[key] = {...v, "au": $0m0(v["au"])}; return top[0];
      case "WorkItem.Implementing": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"])}; return top[0];
      case "WorkItem.Verifying": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"])}; return top[0];
      case "WorkItem.DraftPR": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"])}; return top[0];
      case "WorkItem.Integrated": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"]), "ig": nat_host(v["ig"])}; return top[0];
      case "WorkItem.Deployed": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"]), "ig": nat_host(v["ig"]), "dp": nat_host(v["dp"])}; return top[0];
      case "WorkItem.Accepted": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"]), "ig": nat_host(v["ig"]), "ap": $0m0(v["ap"])}; return top[0];
      case "WorkItem.Merged": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"]), "ig": nat_host(v["ig"]), "ap": $0m0(v["ap"])}; return top[0];
      case "WorkItem.Blocked": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"])}; return top[0];
      case "WorkItem.Interrupted": at = at[key] = {...v, "au": $0m0(v["au"]), "hd": nat_host(v["hd"])}; return top[0];
      case "WorkItem.Abandoned": at[key] = v; return top[0];
      default: throw "bend: WorkItem.Item has no tag " + v?.$ + " (its tags: WorkItem.Proposed, WorkItem.Claimed, WorkItem.Implementing, WorkItem.Verifying, WorkItem.DraftPR, WorkItem.Integrated, WorkItem.Deployed, WorkItem.Accepted, WorkItem.Merged, WorkItem.Blocked, WorkItem.Interrupted, WorkItem.Abandoned); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m3(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Proposed": at[key] = v; return top[0];
      case "WorkItem.Claimed": at = at[key] = {...v, "au": $0m1(v["au"])}; return top[0];
      case "WorkItem.Implementing": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"])}; return top[0];
      case "WorkItem.Verifying": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"])}; return top[0];
      case "WorkItem.DraftPR": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"])}; return top[0];
      case "WorkItem.Integrated": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"]), "ig": BigInt(v["ig"])}; return top[0];
      case "WorkItem.Deployed": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"]), "ig": BigInt(v["ig"]), "dp": BigInt(v["dp"])}; return top[0];
      case "WorkItem.Accepted": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"]), "ig": BigInt(v["ig"]), "ap": $0m1(v["ap"])}; return top[0];
      case "WorkItem.Merged": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"]), "ig": BigInt(v["ig"]), "ap": $0m1(v["ap"])}; return top[0];
      case "WorkItem.Blocked": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"])}; return top[0];
      case "WorkItem.Interrupted": at = at[key] = {...v, "au": $0m1(v["au"]), "hd": BigInt(v["hd"])}; return top[0];
      case "WorkItem.Abandoned": at[key] = v; return top[0];
      default: throw "bend: WorkItem.Item has no tag " + v?.$ + " (its tags: WorkItem.Proposed, WorkItem.Claimed, WorkItem.Implementing, WorkItem.Verifying, WorkItem.DraftPR, WorkItem.Integrated, WorkItem.Deployed, WorkItem.Accepted, WorkItem.Merged, WorkItem.Blocked, WorkItem.Interrupted, WorkItem.Abandoned); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m4(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Receipt": at = at[key] = {...v, "sha": nat_host(v["sha"])}; return top[0];
      default: throw "bend: WorkItem.Receipt has no tag " + v?.$ + " (its tags: WorkItem.Receipt); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m5(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Receipt": at = at[key] = {...v, "sha": BigInt(v["sha"])}; return top[0];
      default: throw "bend: WorkItem.Receipt has no tag " + v?.$ + " (its tags: WorkItem.Receipt); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m6(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Claim": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Start": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Push": at = at[key] = {...v, "a": $0m0(v["a"]), "sha": nat_host(v["sha"])}; return top[0];
      case "WorkItem.Submit": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Verify": at = at[key] = {...v, "a": $0m0(v["a"]), "r": $0m4(v["r"])}; return top[0];
      case "WorkItem.Integrate": at = at[key] = {...v, "a": $0m0(v["a"]), "ish": nat_host(v["ish"]), "r": $0m4(v["r"])}; return top[0];
      case "WorkItem.Deploy": at = at[key] = {...v, "a": $0m0(v["a"]), "served": nat_host(v["served"])}; return top[0];
      case "WorkItem.Observe": at = at[key] = {...v, "served": nat_host(v["served"])}; return top[0];
      case "WorkItem.Accept": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Merge": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Block": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Unblock": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Interrupt": at[key] = v; return top[0];
      case "WorkItem.Resume": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      case "WorkItem.Abandon": at = at[key] = {...v, "a": $0m0(v["a"])}; return top[0];
      default: throw "bend: WorkItem.Ev has no tag " + v?.$ + " (its tags: WorkItem.Claim, WorkItem.Start, WorkItem.Push, WorkItem.Submit, WorkItem.Verify, WorkItem.Integrate, WorkItem.Deploy, WorkItem.Observe, WorkItem.Accept, WorkItem.Merge, WorkItem.Block, WorkItem.Unblock, WorkItem.Interrupt, WorkItem.Resume, WorkItem.Abandon); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m7(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkItem.Claim": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Start": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Push": at = at[key] = {...v, "a": $0m1(v["a"]), "sha": BigInt(v["sha"])}; return top[0];
      case "WorkItem.Submit": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Verify": at = at[key] = {...v, "a": $0m1(v["a"]), "r": $0m5(v["r"])}; return top[0];
      case "WorkItem.Integrate": at = at[key] = {...v, "a": $0m1(v["a"]), "ish": BigInt(v["ish"]), "r": $0m5(v["r"])}; return top[0];
      case "WorkItem.Deploy": at = at[key] = {...v, "a": $0m1(v["a"]), "served": BigInt(v["served"])}; return top[0];
      case "WorkItem.Observe": at = at[key] = {...v, "served": BigInt(v["served"])}; return top[0];
      case "WorkItem.Accept": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Merge": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Block": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Unblock": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Interrupt": at[key] = v; return top[0];
      case "WorkItem.Resume": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      case "WorkItem.Abandon": at = at[key] = {...v, "a": $0m1(v["a"])}; return top[0];
      default: throw "bend: WorkItem.Ev has no tag " + v?.$ + " (its tags: WorkItem.Claim, WorkItem.Start, WorkItem.Push, WorkItem.Submit, WorkItem.Verify, WorkItem.Integrate, WorkItem.Deploy, WorkItem.Observe, WorkItem.Accept, WorkItem.Merge, WorkItem.Block, WorkItem.Unblock, WorkItem.Interrupt, WorkItem.Resume, WorkItem.Abandon); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m8(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m6(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m9(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m7(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m10(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m2(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m11(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m3(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m13(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.W": at = at[key] = {...v, "id": nat_host(v["id"]), "wt": nat_host(v["wt"])}; return top[0];
      default: throw "bend: WorkerSupervision.W has no tag " + v?.$ + " (its tags: WorkerSupervision.W); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m12(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Dispatched": at = at[key] = {...v, "w": $0m13(v["w"])}; return top[0];
      case "WorkerSupervision.Running": at = at[key] = {...v, "w": $0m13(v["w"]), "hb": nat_host(v["hb"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Stalled": at = at[key] = {...v, "w": $0m13(v["w"]), "hb": nat_host(v["hb"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Interrupted": at = at[key] = {...v, "w": $0m13(v["w"]), "at": nat_host(v["at"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Overdue": at = at[key] = {...v, "w": $0m13(v["w"]), "at": nat_host(v["at"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Completed": at = at[key] = {...v, "w": $0m13(v["w"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Resumed": at = at[key] = {...v, "w": $0m13(v["w"]), "by": nat_host(v["by"]), "bg": nat_host(v["bg"])}; return top[0];
      case "WorkerSupervision.Abandoned": at = at[key] = {...v, "w": $0m13(v["w"])}; return top[0];
      case "WorkerSupervision.Integrated": at = at[key] = {...v, "w": $0m13(v["w"])}; return top[0];
      default: throw "bend: WorkerSupervision.St has no tag " + v?.$ + " (its tags: WorkerSupervision.Dispatched, WorkerSupervision.Running, WorkerSupervision.Stalled, WorkerSupervision.Interrupted, WorkerSupervision.Overdue, WorkerSupervision.Completed, WorkerSupervision.Resumed, WorkerSupervision.Abandoned, WorkerSupervision.Integrated); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m15(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.W": at = at[key] = {...v, "id": BigInt(v["id"]), "wt": BigInt(v["wt"])}; return top[0];
      default: throw "bend: WorkerSupervision.W has no tag " + v?.$ + " (its tags: WorkerSupervision.W); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m14(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Dispatched": at = at[key] = {...v, "w": $0m15(v["w"])}; return top[0];
      case "WorkerSupervision.Running": at = at[key] = {...v, "w": $0m15(v["w"]), "hb": BigInt(v["hb"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Stalled": at = at[key] = {...v, "w": $0m15(v["w"]), "hb": BigInt(v["hb"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Interrupted": at = at[key] = {...v, "w": $0m15(v["w"]), "at": BigInt(v["at"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Overdue": at = at[key] = {...v, "w": $0m15(v["w"]), "at": BigInt(v["at"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Completed": at = at[key] = {...v, "w": $0m15(v["w"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Resumed": at = at[key] = {...v, "w": $0m15(v["w"]), "by": BigInt(v["by"]), "bg": BigInt(v["bg"])}; return top[0];
      case "WorkerSupervision.Abandoned": at = at[key] = {...v, "w": $0m15(v["w"])}; return top[0];
      case "WorkerSupervision.Integrated": at = at[key] = {...v, "w": $0m15(v["w"])}; return top[0];
      default: throw "bend: WorkerSupervision.St has no tag " + v?.$ + " (its tags: WorkerSupervision.Dispatched, WorkerSupervision.Running, WorkerSupervision.Stalled, WorkerSupervision.Interrupted, WorkerSupervision.Overdue, WorkerSupervision.Completed, WorkerSupervision.Resumed, WorkerSupervision.Abandoned, WorkerSupervision.Integrated); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m16(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Start": at = at[key] = {...v, "t": nat_host(v["t"])}; return top[0];
      case "WorkerSupervision.Beat": at = at[key] = {...v, "t": nat_host(v["t"])}; return top[0];
      case "WorkerSupervision.Spawn": at[key] = v; return top[0];
      case "WorkerSupervision.Reap": at[key] = v; return top[0];
      case "WorkerSupervision.Tick": at = at[key] = {...v, "now": nat_host(v["now"])}; return top[0];
      case "WorkerSupervision.Finish": at[key] = v; return top[0];
      case "WorkerSupervision.Interrupt": at = at[key] = {...v, "t": nat_host(v["t"])}; return top[0];
      case "WorkerSupervision.Resume": at = at[key] = {...v, "by": nat_host(v["by"])}; return top[0];
      case "WorkerSupervision.Abandon": at[key] = v; return top[0];
      case "WorkerSupervision.Integrate": at[key] = v; return top[0];
      default: throw "bend: WorkerSupervision.Ev has no tag " + v?.$ + " (its tags: WorkerSupervision.Start, WorkerSupervision.Beat, WorkerSupervision.Spawn, WorkerSupervision.Reap, WorkerSupervision.Tick, WorkerSupervision.Finish, WorkerSupervision.Interrupt, WorkerSupervision.Resume, WorkerSupervision.Abandon, WorkerSupervision.Integrate); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m17(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Start": at = at[key] = {...v, "t": BigInt(v["t"])}; return top[0];
      case "WorkerSupervision.Beat": at = at[key] = {...v, "t": BigInt(v["t"])}; return top[0];
      case "WorkerSupervision.Spawn": at[key] = v; return top[0];
      case "WorkerSupervision.Reap": at[key] = v; return top[0];
      case "WorkerSupervision.Tick": at = at[key] = {...v, "now": BigInt(v["now"])}; return top[0];
      case "WorkerSupervision.Finish": at[key] = v; return top[0];
      case "WorkerSupervision.Interrupt": at = at[key] = {...v, "t": BigInt(v["t"])}; return top[0];
      case "WorkerSupervision.Resume": at = at[key] = {...v, "by": BigInt(v["by"])}; return top[0];
      case "WorkerSupervision.Abandon": at[key] = v; return top[0];
      case "WorkerSupervision.Integrate": at[key] = v; return top[0];
      default: throw "bend: WorkerSupervision.Ev has no tag " + v?.$ + " (its tags: WorkerSupervision.Start, WorkerSupervision.Beat, WorkerSupervision.Spawn, WorkerSupervision.Reap, WorkerSupervision.Tick, WorkerSupervision.Finish, WorkerSupervision.Interrupt, WorkerSupervision.Resume, WorkerSupervision.Abandon, WorkerSupervision.Integrate); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m18(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m16(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m19(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": $0m17(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m20(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Free": at[key] = v; return top[0];
      case "WorkerSupervision.Held": at = at[key] = {...v, "o": nat_host(v["o"])}; return top[0];
      default: throw "bend: WorkerSupervision.Lease has no tag " + v?.$ + " (its tags: WorkerSupervision.Free, WorkerSupervision.Held); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m21(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Free": at[key] = v; return top[0];
      case "WorkerSupervision.Held": at = at[key] = {...v, "o": BigInt(v["o"])}; return top[0];
      default: throw "bend: WorkerSupervision.Lease has no tag " + v?.$ + " (its tags: WorkerSupervision.Free, WorkerSupervision.Held); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m22(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Acquire": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Release": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Reclaim": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      default: throw "bend: WorkerSupervision.LEv has no tag " + v?.$ + " (its tags: WorkerSupervision.Acquire, WorkerSupervision.Release, WorkerSupervision.Reclaim); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m23(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Acquire": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Release": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Reclaim": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      default: throw "bend: WorkerSupervision.LEv has no tag " + v?.$ + " (its tags: WorkerSupervision.Acquire, WorkerSupervision.Release, WorkerSupervision.Reclaim); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m24(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.NoEff": at[key] = v; return top[0];
      case "WorkerSupervision.Installed": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Typed": at = at[key] = {...v, "a": nat_host(v["a"]), "app": nat_host(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.Eff has no tag " + v?.$ + " (its tags: WorkerSupervision.NoEff, WorkerSupervision.Installed, WorkerSupervision.Typed); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m25(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.NoEff": at[key] = v; return top[0];
      case "WorkerSupervision.Installed": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Typed": at = at[key] = {...v, "a": BigInt(v["a"]), "app": BigInt(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.Eff has no tag " + v?.$ + " (its tags: WorkerSupervision.NoEff, WorkerSupervision.Installed, WorkerSupervision.Typed); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m26(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Unknown": at[key] = v; return top[0];
      case "WorkerSupervision.Seen": at = at[key] = {...v, "app": nat_host(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.Fg has no tag " + v?.$ + " (its tags: WorkerSupervision.Unknown, WorkerSupervision.Seen); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m27(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Unknown": at[key] = v; return top[0];
      case "WorkerSupervision.Seen": at = at[key] = {...v, "app": BigInt(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.Fg has no tag " + v?.$ + " (its tags: WorkerSupervision.Unknown, WorkerSupervision.Seen); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m28(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Lock": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Unlock": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Peek": at = at[key] = {...v, "app": nat_host(v["app"])}; return top[0];
      case "WorkerSupervision.Install": at = at[key] = {...v, "a": nat_host(v["a"])}; return top[0];
      case "WorkerSupervision.Input": at = at[key] = {...v, "a": nat_host(v["a"]), "app": nat_host(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.PEv has no tag " + v?.$ + " (its tags: WorkerSupervision.Lock, WorkerSupervision.Unlock, WorkerSupervision.Peek, WorkerSupervision.Install, WorkerSupervision.Input); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m29(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Lock": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Unlock": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Peek": at = at[key] = {...v, "app": BigInt(v["app"])}; return top[0];
      case "WorkerSupervision.Install": at = at[key] = {...v, "a": BigInt(v["a"])}; return top[0];
      case "WorkerSupervision.Input": at = at[key] = {...v, "a": BigInt(v["a"]), "app": BigInt(v["app"])}; return top[0];
      default: throw "bend: WorkerSupervision.PEv has no tag " + v?.$ + " (its tags: WorkerSupervision.Lock, WorkerSupervision.Unlock, WorkerSupervision.Peek, WorkerSupervision.Install, WorkerSupervision.Input); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m30(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Dev": at = at[key] = {...v, "lk": $0m20(v["lk"]), "fg": $0m26(v["fg"])}; return top[0];
      default: throw "bend: WorkerSupervision.Device has no tag " + v?.$ + " (its tags: WorkerSupervision.Dev); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m31(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "WorkerSupervision.Dev": at = at[key] = {...v, "lk": $0m21(v["lk"]), "fg": $0m27(v["fg"])}; return top[0];
      default: throw "bend: WorkerSupervision.Device has no tag " + v?.$ + " (its tags: WorkerSupervision.Dev); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m32(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "IntegrationOwner.Free": at[key] = v; return top[0];
      case "IntegrationOwner.Held": at = at[key] = {...v, "owner": nat_host(v["owner"]), "until": nat_host(v["until"])}; return top[0];
      default: throw "bend: IntegrationOwner.Lease has no tag " + v?.$ + " (its tags: IntegrationOwner.Free, IntegrationOwner.Held); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m33(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "IntegrationOwner.Free": at[key] = v; return top[0];
      case "IntegrationOwner.Held": at = at[key] = {...v, "owner": BigInt(v["owner"]), "until": BigInt(v["until"])}; return top[0];
      default: throw "bend: IntegrationOwner.Lease has no tag " + v?.$ + " (its tags: IntegrationOwner.Free, IntegrationOwner.Held); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m34(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": nat_host(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m35(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Nil": at[key] = v; return top[0];
      case "Con": at = at[key] = {...v, "head": BigInt(v["head"])}; key = "tail"; v = v[key]; continue;
      default: throw "bend: List has no tag " + v?.$ + " (its tags: Nil, Con); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m36(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.NHealthy": at[key] = v; return top[0];
      case "Ops.NBad": at = at[key] = {...v, "since": nat_host(v["since"])}; return top[0];
      case "Ops.NNotified": at = at[key] = {...v, "since": nat_host(v["since"])}; return top[0];
      default: throw "bend: Ops.NSt has no tag " + v?.$ + " (its tags: Ops.NHealthy, Ops.NBad, Ops.NNotified); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m37(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.NHealthy": at[key] = v; return top[0];
      case "Ops.NBad": at = at[key] = {...v, "since": BigInt(v["since"])}; return top[0];
      case "Ops.NNotified": at = at[key] = {...v, "since": BigInt(v["since"])}; return top[0];
      default: throw "bend: Ops.NSt has no tag " + v?.$ + " (its tags: Ops.NHealthy, Ops.NBad, Ops.NNotified); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m38(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.NProbe": at = at[key] = {...v, "now": nat_host(v["now"])}; return top[0];
      default: throw "bend: Ops.NEv has no tag " + v?.$ + " (its tags: Ops.NProbe); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m39(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.NProbe": at = at[key] = {...v, "now": BigInt(v["now"])}; return top[0];
      default: throw "bend: Ops.NEv has no tag " + v?.$ + " (its tags: Ops.NProbe); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m40(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.RActive": at = at[key] = {...v, "gw": nat_host(v["gw"])}; return top[0];
      case "Ops.RInterrupted": at = at[key] = {...v, "gw": nat_host(v["gw"])}; return top[0];
      case "Ops.RFailed": at[key] = v; return top[0];
      case "Ops.RDone": at[key] = v; return top[0];
      case "Ops.RResumed": at[key] = v; return top[0];
      case "Ops.RReported": at[key] = v; return top[0];
      default: throw "bend: Ops.RSt has no tag " + v?.$ + " (its tags: Ops.RActive, Ops.RInterrupted, Ops.RFailed, Ops.RDone, Ops.RResumed, Ops.RReported); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m41(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.RActive": at = at[key] = {...v, "gw": BigInt(v["gw"])}; return top[0];
      case "Ops.RInterrupted": at = at[key] = {...v, "gw": BigInt(v["gw"])}; return top[0];
      case "Ops.RFailed": at[key] = v; return top[0];
      case "Ops.RDone": at[key] = v; return top[0];
      case "Ops.RResumed": at[key] = v; return top[0];
      case "Ops.RReported": at[key] = v; return top[0];
      default: throw "bend: Ops.RSt has no tag " + v?.$ + " (its tags: Ops.RActive, Ops.RInterrupted, Ops.RFailed, Ops.RDone, Ops.RResumed, Ops.RReported); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m42(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.GwRestart": at = at[key] = {...v, "gw": nat_host(v["gw"])}; return top[0];
      case "Ops.RunError": at[key] = v; return top[0];
      case "Ops.RunDone": at[key] = v; return top[0];
      case "Ops.ResumeRun": at[key] = v; return top[0];
      case "Ops.ReportRun": at[key] = v; return top[0];
      default: throw "bend: Ops.REv has no tag " + v?.$ + " (its tags: Ops.GwRestart, Ops.RunError, Ops.RunDone, Ops.ResumeRun, Ops.ReportRun); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}

function $0m43(v) {
  const top = [v];
  for (let at = top, key = 0;;) {
    switch (v.$) {
      case "Ops.GwRestart": at = at[key] = {...v, "gw": BigInt(v["gw"])}; return top[0];
      case "Ops.RunError": at[key] = v; return top[0];
      case "Ops.RunDone": at[key] = v; return top[0];
      case "Ops.ResumeRun": at[key] = v; return top[0];
      case "Ops.ReportRun": at[key] = v; return top[0];
      default: throw "bend: Ops.REv has no tag " + v?.$ + " (its tags: Ops.GwRestart, Ops.RunError, Ops.RunDone, Ops.ResumeRun, Ops.ReportRun); a tag names its constructor as the"
      + " loading file sees it, which a later version will make the same"
      + " everywhere (#1105)";
    }
  }
}
export default {
  "WorkItem.coder": run_lib((a0) => { const r = (run_loop($WorkItem$coder$((a0)))); (a0); return r; }, 1),
  "WorkItem.is_ci": run_lib((a0) => { const r = (run_loop($WorkItem$is_ci$((a0)))); (a0); return r; }, 1),
  "WorkItem.is_owner": run_lib((a0) => { const r = (run_loop($WorkItem$is_owner$((a0)))); (a0); return r; }, 1),
  "WorkItem.operator": run_lib((a0) => { const r = (run_loop($WorkItem$operator$((a0)))); (a0); return r; }, 1),
  "WorkItem.merger": run_lib((a0) => { const r = (run_loop($WorkItem$merger$((a0)))); (a0); return r; }, 1),
  "WorkItem.steward": run_lib((a0) => { const r = (run_loop($WorkItem$steward$((a0)))); (a0); return r; }, 1),
  "WorkItem.rid": run_lib((a0) => { const r = BigInt(run_loop($WorkItem$rid$($0m0(a0)))); $0m1(a0); return r; }, 1),
  "WorkItem.rrole": run_lib((a0) => { const r = (run_loop($WorkItem$rrole$($0m0(a0)))); $0m1(a0); return r; }, 1),
  "WorkItem.same": run_lib((a0, a1) => { const r = (run_loop($WorkItem$same$($0m0(a0), $0m0(a1)))); $0m1(a0); $0m1(a1); return r; }, 2),
  "WorkItem.other": run_lib((a0, a1) => { const r = (run_loop($WorkItem$other$($0m0(a0), $0m0(a1)))); $0m1(a0); $0m1(a1); return r; }, 2),
  "WorkItem.pick": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$pick$((a0), $0m2(a1), $0m2(a2)))); (a0); $0m3(a1); $0m3(a2); return r; }, 3),
  "WorkItem.verify_out": run_lib((a0, a1, a2, a3) => { const r = $0m3(run_loop($WorkItem$verify_out$((a0), (a1), $0m0(a2), nat_host(a3)))); (a0); (a1); $0m1(a2); BigInt(a3); return r; }, 4),
  "WorkItem.verify_gate": run_lib((a0, a1) => { const r = (run_loop($WorkItem$verify_gate$($0m0(a0), $0m0(a1)))); $0m1(a0); $0m1(a1); return r; }, 2),
  "WorkItem.receipt_good": run_lib((a0, a1) => { const r = (run_loop($WorkItem$receipt_good$($0m4(a0), nat_host(a1)))); $0m5(a0); BigInt(a1); return r; }, 2),
  "WorkItem.integrate_gate": run_lib((a0, a1) => { const r = (run_loop($WorkItem$integrate_gate$($0m0(a0), $0m0(a1)))); $0m1(a0); $0m1(a1); return r; }, 2),
  "WorkItem.accept_gate": run_lib((a0, a1) => { const r = (run_loop($WorkItem$accept_gate$($0m0(a0), $0m0(a1)))); $0m1(a0); $0m1(a1); return r; }, 2),
  "WorkItem.from_proposed": run_lib((a0) => { const r = $0m3(run_loop($WorkItem$from_proposed$($0m6(a0)))); $0m7(a0); return r; }, 1),
  "WorkItem.from_claimed": run_lib((a0, a1) => { const r = $0m3(run_loop($WorkItem$from_claimed$($0m0(a0), $0m6(a1)))); $0m1(a0); $0m7(a1); return r; }, 2),
  "WorkItem.from_implementing": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$from_implementing$($0m0(a0), nat_host(a1), $0m6(a2)))); $0m1(a0); BigInt(a1); $0m7(a2); return r; }, 3),
  "WorkItem.from_verifying": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$from_verifying$($0m0(a0), nat_host(a1), $0m6(a2)))); $0m1(a0); BigInt(a1); $0m7(a2); return r; }, 3),
  "WorkItem.integrate_out": run_lib((a0, a1, a2, a3) => { const r = $0m3(run_loop($WorkItem$integrate_out$((a0), $0m0(a1), nat_host(a2), nat_host(a3)))); (a0); $0m1(a1); BigInt(a2); BigInt(a3); return r; }, 4),
  "WorkItem.from_draft": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$from_draft$($0m0(a0), nat_host(a1), $0m6(a2)))); $0m1(a0); BigInt(a1); $0m7(a2); return r; }, 3),
  "WorkItem.deploy_out": run_lib((a0, a1, a2, a3, a4) => { const r = $0m3(run_loop($WorkItem$deploy_out$((a0), $0m0(a1), nat_host(a2), nat_host(a3), nat_host(a4)))); (a0); $0m1(a1); BigInt(a2); BigInt(a3); BigInt(a4); return r; }, 5),
  "WorkItem.from_integrated": run_lib((a0, a1, a2, a3) => { const r = $0m3(run_loop($WorkItem$from_integrated$($0m0(a0), nat_host(a1), nat_host(a2), $0m6(a3)))); $0m1(a0); BigInt(a1); BigInt(a2); $0m7(a3); return r; }, 4),
  "WorkItem.observe_out": run_lib((a0, a1, a2, a3, a4) => { const r = $0m3(run_loop($WorkItem$observe_out$((a0), $0m0(a1), nat_host(a2), nat_host(a3), nat_host(a4)))); (a0); $0m1(a1); BigInt(a2); BigInt(a3); BigInt(a4); return r; }, 5),
  "WorkItem.accept_out": run_lib((a0, a1, a2, a3, a4, a5) => { const r = $0m3(run_loop($WorkItem$accept_out$((a0), $0m0(a1), nat_host(a2), nat_host(a3), nat_host(a4), $0m0(a5)))); (a0); $0m1(a1); BigInt(a2); BigInt(a3); BigInt(a4); $0m1(a5); return r; }, 6),
  "WorkItem.from_deployed": run_lib((a0, a1, a2, a3, a4) => { const r = $0m3(run_loop($WorkItem$from_deployed$($0m0(a0), nat_host(a1), nat_host(a2), nat_host(a3), $0m6(a4)))); $0m1(a0); BigInt(a1); BigInt(a2); BigInt(a3); $0m7(a4); return r; }, 5),
  "WorkItem.from_accepted": run_lib((a0, a1, a2, a3, a4) => { const r = $0m3(run_loop($WorkItem$from_accepted$($0m0(a0), nat_host(a1), nat_host(a2), $0m0(a3), $0m6(a4)))); $0m1(a0); BigInt(a1); BigInt(a2); $0m1(a3); $0m7(a4); return r; }, 5),
  "WorkItem.from_blocked": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$from_blocked$($0m0(a0), nat_host(a1), $0m6(a2)))); $0m1(a0); BigInt(a1); $0m7(a2); return r; }, 3),
  "WorkItem.from_interrupted": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$from_interrupted$($0m0(a0), nat_host(a1), $0m6(a2)))); $0m1(a0); BigInt(a1); $0m7(a2); return r; }, 3),
  "WorkItem.step": run_lib((a0, a1) => { const r = $0m3(run_loop($WorkItem$step$($0m2(a0), $0m6(a1)))); $0m3(a0); $0m7(a1); return r; }, 2),
  "WorkItem.run": run_lib((a0, a1) => { const r = $0m3(run_loop($WorkItem$run$($0m8(a0), $0m2(a1)))); $0m9(a0); $0m3(a1); return r; }, 2),
  "WorkItem.is_off": run_lib((a0) => { const r = (run_loop($WorkItem$is_off$((a0)))); (a0); return r; }, 1),
  "WorkItem.owner_event": run_lib((a0) => { const r = (run_loop($WorkItem$owner_event$($0m6(a0)))); $0m7(a0); return r; }, 1),
  "WorkItem.needs_kevin": run_lib((a0) => { const r = (run_loop($WorkItem$needs_kevin$($0m2(a0)))); $0m3(a0); return r; }, 1),
  "WorkItem.astep.go": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$astep$go$((a0), $0m2(a1), $0m6(a2)))); (a0); $0m3(a1); $0m7(a2); return r; }, 3),
  "WorkItem.astep": run_lib((a0, a1, a2) => { const r = $0m3(run_loop($WorkItem$astep$((a0), $0m2(a1), $0m6(a2)))); (a0); $0m3(a1); $0m7(a2); return r; }, 3),
  "WorkItem.board_step": run_lib((a0, a1, a2, a3) => { const r = $0m11(run_loop($WorkItem$board_step$($0m10(a0), nat_host(a1), (a2), $0m6(a3)))); $0m11(a0); BigInt(a1); (a2); $0m7(a3); return r; }, 4),
  "WorkItem.nth": run_lib((a0, a1) => { const r = $0m3(run_loop($WorkItem$nth$($0m10(a0), nat_host(a1)))); $0m11(a0); BigInt(a1); return r; }, 2),
  "WorkerSupervision.pick": run_lib((a0, a1, a2) => { const r = $0m14(run_loop($WorkerSupervision$pick$((a0), $0m12(a1), $0m12(a2)))); (a0); $0m14(a1); $0m14(a2); return r; }, 3),
  "WorkerSupervision.heavy": run_lib((a0) => { const r = (run_loop($WorkerSupervision$heavy$((a0)))); (a0); return r; }, 1),
  "WorkerSupervision.declared": run_lib((a0) => { const r = (run_loop($WorkerSupervision$declared$((a0)))); (a0); return r; }, 1),
  "WorkerSupervision.on_groot": run_lib((a0) => { const r = (run_loop($WorkerSupervision$on_groot$((a0)))); (a0); return r; }, 1),
  "WorkerSupervision.wload": run_lib((a0) => { const r = (run_loop($WorkerSupervision$wload$($0m13(a0)))); $0m15(a0); return r; }, 1),
  "WorkerSupervision.wexc": run_lib((a0) => { const r = (run_loop($WorkerSupervision$wexc$($0m13(a0)))); $0m15(a0); return r; }, 1),
  "WorkerSupervision.placed": run_lib((a0, a1) => { const r = (run_loop($WorkerSupervision$placed$($0m13(a0), (a1)))); $0m15(a0); (a1); return r; }, 2),
  "WorkerSupervision.dec": run_lib((a0) => { const r = BigInt(run_loop($WorkerSupervision$dec$(nat_host(a0)))); BigInt(a0); return r; }, 1),
  "WorkerSupervision.is_zero": run_lib((a0) => { const r = (run_loop($WorkerSupervision$is_zero$(nat_host(a0)))); BigInt(a0); return r; }, 1),
  "WorkerSupervision.late": run_lib((a0, a1, a2) => { const r = (run_loop($WorkerSupervision$late$(nat_host(a0), nat_host(a1), nat_host(a2)))); BigInt(a0); BigInt(a1); BigInt(a2); return r; }, 3),
  "WorkerSupervision.from_dispatched": run_lib((a0, a1) => { const r = $0m14(run_loop($WorkerSupervision$from_dispatched$($0m13(a0), $0m16(a1)))); $0m15(a0); $0m17(a1); return r; }, 2),
  "WorkerSupervision.from_running": run_lib((a0, a1, a2, a3, a4, a5) => { const r = $0m14(run_loop($WorkerSupervision$from_running$($0m13(a0), (a1), nat_host(a2), nat_host(a3), $0m16(a4), nat_host(a5)))); $0m15(a0); (a1); BigInt(a2); BigInt(a3); $0m17(a4); BigInt(a5); return r; }, 6),
  "WorkerSupervision.from_stalled": run_lib((a0, a1, a2, a3, a4, a5) => { const r = $0m14(run_loop($WorkerSupervision$from_stalled$($0m13(a0), (a1), nat_host(a2), nat_host(a3), $0m16(a4), nat_host(a5)))); $0m15(a0); (a1); BigInt(a2); BigInt(a3); $0m17(a4); BigInt(a5); return r; }, 6),
  "WorkerSupervision.from_interrupted": run_lib((a0, a1, a2, a3, a4) => { const r = $0m14(run_loop($WorkerSupervision$from_interrupted$($0m13(a0), nat_host(a1), nat_host(a2), $0m16(a3), nat_host(a4)))); $0m15(a0); BigInt(a1); BigInt(a2); $0m17(a3); BigInt(a4); return r; }, 5),
  "WorkerSupervision.from_overdue": run_lib((a0, a1, a2, a3) => { const r = $0m14(run_loop($WorkerSupervision$from_overdue$($0m13(a0), nat_host(a1), nat_host(a2), $0m16(a3)))); $0m15(a0); BigInt(a1); BigInt(a2); $0m17(a3); return r; }, 4),
  "WorkerSupervision.from_completed": run_lib((a0, a1, a2) => { const r = $0m14(run_loop($WorkerSupervision$from_completed$($0m13(a0), nat_host(a1), $0m16(a2)))); $0m15(a0); BigInt(a1); $0m17(a2); return r; }, 3),
  "WorkerSupervision.step": run_lib((a0, a1, a2) => { const r = $0m14(run_loop($WorkerSupervision$step$($0m12(a0), $0m16(a1), nat_host(a2)))); $0m14(a0); $0m17(a1); BigInt(a2); return r; }, 3),
  "WorkerSupervision.run": run_lib((a0, a1, a2) => { const r = $0m14(run_loop($WorkerSupervision$run$($0m18(a0), nat_host(a1), $0m12(a2)))); $0m19(a0); BigInt(a1); $0m14(a2); return r; }, 3),
  "WorkerSupervision.needs_kevin": run_lib((a0) => { const r = (run_loop($WorkerSupervision$needs_kevin$($0m12(a0)))); $0m14(a0); return r; }, 1),
  "WorkerSupervision.lpick": run_lib((a0, a1, a2) => { const r = $0m21(run_loop($WorkerSupervision$lpick$((a0), $0m20(a1), $0m20(a2)))); (a0); $0m21(a1); $0m21(a2); return r; }, 3),
  "WorkerSupervision.lfree": run_lib((a0) => { const r = $0m21(run_loop($WorkerSupervision$lfree$($0m22(a0)))); $0m23(a0); return r; }, 1),
  "WorkerSupervision.lheld": run_lib((a0, a1) => { const r = $0m21(run_loop($WorkerSupervision$lheld$(nat_host(a0), $0m22(a1)))); BigInt(a0); $0m23(a1); return r; }, 2),
  "WorkerSupervision.lstep": run_lib((a0, a1) => { const r = $0m21(run_loop($WorkerSupervision$lstep$($0m20(a0), $0m22(a1)))); $0m21(a0); $0m23(a1); return r; }, 2),
  "WorkerSupervision.holds": run_lib((a0, a1) => { const r = (run_loop($WorkerSupervision$holds$($0m20(a0), nat_host(a1)))); $0m21(a0); BigInt(a1); return r; }, 2),
  "WorkerSupervision.epick": run_lib((a0, a1, a2) => { const r = $0m25(run_loop($WorkerSupervision$epick$((a0), $0m24(a1), $0m24(a2)))); (a0); $0m25(a1); $0m25(a2); return r; }, 3),
  "WorkerSupervision.fg_is": run_lib((a0, a1) => { const r = (run_loop($WorkerSupervision$fg_is$($0m26(a0), nat_host(a1)))); $0m27(a0); BigInt(a1); return r; }, 2),
  "WorkerSupervision.dev_eff": run_lib((a0, a1, a2) => { const r = $0m25(run_loop($WorkerSupervision$dev_eff$($0m20(a0), $0m26(a1), $0m28(a2)))); $0m21(a0); $0m27(a1); $0m29(a2); return r; }, 3),
  "WorkerSupervision.peff": run_lib((a0, a1) => { const r = $0m25(run_loop($WorkerSupervision$peff$($0m30(a0), $0m28(a1)))); $0m31(a0); $0m29(a1); return r; }, 2),
  "WorkerSupervision.dev_step": run_lib((a0, a1, a2) => { const r = $0m31(run_loop($WorkerSupervision$dev_step$($0m20(a0), $0m26(a1), $0m28(a2)))); $0m21(a0); $0m27(a1); $0m29(a2); return r; }, 3),
  "WorkerSupervision.pstep": run_lib((a0, a1) => { const r = $0m31(run_loop($WorkerSupervision$pstep$($0m30(a0), $0m28(a1)))); $0m31(a0); $0m29(a1); return r; }, 2),
  "IntegrationOwner.pick": run_lib((a0, a1, a2) => { const r = (run_loop($IntegrationOwner$pick$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "IntegrationOwner.advance": run_lib((a0, a1) => { const r = (run_loop($IntegrationOwner$advance$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "IntegrationOwner.observe": run_lib((a0, a1) => { const r = (run_loop($IntegrationOwner$observe$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "IntegrationOwner.active": run_lib((a0, a1) => { const r = (run_loop($IntegrationOwner$active$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "IntegrationOwner.step": run_lib((a0, a1) => { const r = (run_loop($IntegrationOwner$step$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "IntegrationOwner.overdue": run_lib((a0, a1, a2) => { const r = (run_loop($IntegrationOwner$overdue$(nat_host(a0), (a1), (a2)))); BigInt(a0); (a1); (a2); return r; }, 3),
  "IntegrationOwner.lpick": run_lib((a0, a1, a2) => { const r = $0m33(run_loop($IntegrationOwner$lpick$((a0), $0m32(a1), $0m32(a2)))); (a0); $0m33(a1); $0m33(a2); return r; }, 3),
  "IntegrationOwner.acquire": run_lib((a0, a1, a2, a3) => { const r = $0m33(run_loop($IntegrationOwner$acquire$($0m32(a0), nat_host(a1), nat_host(a2), nat_host(a3)))); $0m33(a0); BigInt(a1); BigInt(a2); BigInt(a3); return r; }, 4),
  "Ops.groot_class": run_lib((a0) => { const r = (run_loop($Ops$groot_class$((a0)))); (a0); return r; }, 1),
  "Ops.admits": run_lib((a0, a1) => { const r = (run_loop($Ops$admits$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.place_phone": run_lib((a0) => { const r = (run_loop($Ops$place_phone$((a0)))); (a0); return r; }, 1),
  "Ops.place_off": run_lib((a0, a1) => { const r = (run_loop($Ops$place_off$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.place_by": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$place_by$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "Ops.place": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$place$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "Ops.runs_on_groot": run_lib((a0) => { const r = (run_loop($Ops$runs_on_groot$((a0)))); (a0); return r; }, 1),
  "Ops.served_allows": run_lib((a0, a1) => { const r = (run_loop($Ops$served_allows$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.wt_allows": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$wt_allows$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "Ops.review_ok": run_lib((a0, a1) => { const r = (run_loop($Ops$review_ok$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.pre_ok": run_lib((a0, a1, a2, a3) => { const r = (run_loop($Ops$pre_ok$((a0), (a1), (a2), (a3)))); (a0); (a1); (a2); (a3); return r; }, 4),
  "Ops.ready": run_lib((a0, a1) => { const r = (run_loop($Ops$ready$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.finish": run_lib((a0) => { const r = (run_loop($Ops$finish$((a0)))); (a0); return r; }, 1),
  "Ops.go": run_lib((a0, a1) => { const r = (run_loop($Ops$go$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.decide": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$decide$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "Ops.rollout": run_lib((a0, a1) => { const r = (run_loop($Ops$rollout$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.promoted": run_lib((a0) => { const r = (run_loop($Ops$promoted$((a0)))); (a0); return r; }, 1),
  "Ops.touched": run_lib((a0) => { const r = (run_loop($Ops$touched$((a0)))); (a0); return r; }, 1),
  "Ops.vis_private": run_lib((a0) => { const r = (run_loop($Ops$vis_private$((a0)))); (a0); return r; }, 1),
  "Ops.push_allows": run_lib((a0, a1) => { const r = (run_loop($Ops$push_allows$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.phone_allows": run_lib((a0, a1) => { const r = (run_loop($Ops$phone_allows$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "Ops.mem": run_lib((a0, a1) => { const r = (run_loop($Ops$mem$(nat_host(a0), $0m34(a1)))); BigInt(a0); $0m35(a1); return r; }, 2),
  "Ops.a11y_ok": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$a11y_ok$($0m34(a0), $0m34(a1), $0m34(a2)))); $0m35(a0); $0m35(a1); $0m35(a2); return r; }, 3),
  "Ops.route_ok": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$route_ok$((a0), (a1), (a2)))); (a0); (a1); (a2); return r; }, 3),
  "Ops.late": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$late$(nat_host(a0), nat_host(a1), nat_host(a2)))); BigInt(a0); BigInt(a1); BigInt(a2); return r; }, 3),
  "Ops.npick": run_lib((a0, a1, a2) => { const r = $0m37(run_loop($Ops$npick$((a0), $0m36(a1), $0m36(a2)))); (a0); $0m37(a1); $0m37(a2); return r; }, 3),
  "Ops.from_healthy": run_lib((a0) => { const r = $0m37(run_loop($Ops$from_healthy$($0m38(a0)))); $0m39(a0); return r; }, 1),
  "Ops.from_bad": run_lib((a0, a1, a2) => { const r = $0m37(run_loop($Ops$from_bad$(nat_host(a0), $0m38(a1), nat_host(a2)))); BigInt(a0); $0m39(a1); BigInt(a2); return r; }, 3),
  "Ops.from_notified": run_lib((a0, a1) => { const r = $0m37(run_loop($Ops$from_notified$(nat_host(a0), $0m38(a1)))); BigInt(a0); $0m39(a1); return r; }, 2),
  "Ops.nstep": run_lib((a0, a1, a2) => { const r = $0m37(run_loop($Ops$nstep$($0m36(a0), $0m38(a1), nat_host(a2)))); $0m37(a0); $0m39(a1); BigInt(a2); return r; }, 3),
  "Ops.bad_eff": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$bad_eff$(nat_host(a0), $0m38(a1), nat_host(a2)))); BigInt(a0); $0m39(a1); BigInt(a2); return r; }, 3),
  "Ops.neff": run_lib((a0, a1, a2) => { const r = (run_loop($Ops$neff$($0m36(a0), $0m38(a1), nat_host(a2)))); $0m37(a0); $0m39(a1); BigInt(a2); return r; }, 3),
  "Ops.notified": run_lib((a0) => { const r = (run_loop($Ops$notified$($0m36(a0)))); $0m37(a0); return r; }, 1),
  "Ops.rpick": run_lib((a0, a1, a2) => { const r = $0m41(run_loop($Ops$rpick$((a0), $0m40(a1), $0m40(a2)))); (a0); $0m41(a1); $0m41(a2); return r; }, 3),
  "Ops.ract": run_lib((a0, a1) => { const r = $0m41(run_loop($Ops$ract$(nat_host(a0), $0m42(a1)))); BigInt(a0); $0m43(a1); return r; }, 2),
  "Ops.rint": run_lib((a0, a1) => { const r = $0m41(run_loop($Ops$rint$(nat_host(a0), $0m42(a1)))); BigInt(a0); $0m43(a1); return r; }, 2),
  "Ops.rstep": run_lib((a0, a1) => { const r = $0m41(run_loop($Ops$rstep$($0m40(a0), $0m42(a1)))); $0m41(a0); $0m43(a1); return r; }, 2),
  "Ops.rfailed": run_lib((a0) => { const r = (run_loop($Ops$rfailed$($0m40(a0)))); $0m41(a0); return r; }, 1),
  "OpsLayer.by_bool": run_lib((a0) => { const r = (run_loop($OpsLayer$by_bool$((a0)))); (a0); return r; }, 1),
  "OpsLayer.by_place": run_lib((a0) => { const r = (run_loop($OpsLayer$by_place$((a0)))); (a0); return r; }, 1),
  "OpsLayer.by_out": run_lib((a0) => { const r = (run_loop($OpsLayer$by_out$((a0)))); (a0); return r; }, 1),
  "OpsLayer.gate_step": run_lib((a0, a1) => { const r = (run_loop($OpsLayer$gate_step$((a0), (a1)))); (a0); (a1); return r; }, 2),
  "abi_version": run_lib(() => { const r = (run_loop($abi_version$()));  return r; }, 0),
};

export const bendMetadata = {"schema":1,"title":"Bend statecharts for agent work · Hapsland layers","scope":"Three Bend control-plane loops. Loop 3 snapshot tapes derive from the integration inventory; guard probes are what-if, never invented historical deployments. Runtime/build SHA gaps remain unverified.","trustBoundary":"Bend decides every next state. The adapter only converts JSON to Bend constructors and back, and labels an unchanged state with the guarding law from this file. A replay is not an authorization, an admission or verified success, and it does not observe any live host.","machines":{"work-item":{"title":"Loop 1 · work-item lifecycle","stateType":"WorkItem.Item","eventType":"WorkItem.Ev","step":"WorkItem.astep(availability, state, event)","plane":"work-item","facts":{"availability":{"type":"WorkItem.Avail","default":"DeepWork","description":"Kevin's self-reported availability (ROLES-v0): an owner action while Off is held in the needs-Kevin queue (L7)."}}},"worker":{"title":"Loop 2 · worker supervision","stateType":"WorkerSupervision.St","eventType":"WorkerSupervision.Ev","step":"WorkerSupervision.step(state, event, limit)","plane":"worker","facts":{"limit":{"type":"Nat","default":120,"description":"Supervision limit in minutes (the report used 2 h)."}}},"lease":{"title":"Loop 2 · worktree lease / install lock","stateType":"WorkerSupervision.Lease","eventType":"WorkerSupervision.LEv","step":"WorkerSupervision.lstep(lease, event)","plane":"shared","facts":{}},"device":{"title":"Loop 2 · owner's S25","stateType":"WorkerSupervision.Device","eventType":"WorkerSupervision.PEv","step":"WorkerSupervision.pstep(device, event) + WorkerSupervision.peff(device, event)","plane":"shared","facts":{}},"integration":{"title":"Loop 3 · integration owner","stateType":"IntegrationOwner.St","eventType":"IntegrationOwner.Ev","step":"IntegrationOwner.step(state, event)","plane":"integration","facts":{}},"ops-gates":{"title":"Ops · gates O1–O5, O7","stateType":"OpsLayer.GSt","eventType":"OpsLayer.GEv","step":"OpsLayer.gate_step(state, event) over Ops.place / wt_allows / rollout / push_allows / phone_allows / route_ok","plane":"ops","facts":{}},"node-health":{"title":"Ops · O8 node health","stateType":"Ops.NSt","eventType":"Ops.NEv","step":"Ops.nstep(state, event, limit) + Ops.neff(state, event, limit)","plane":"ops","facts":{"limit":{"type":"Nat","default":1800,"description":"Seconds unhealthy before the one owner notification (30 min)."}}},"gateway-run":{"title":"Ops · O9 headless run","stateType":"Ops.RSt","eventType":"Ops.REv","step":"Ops.rstep(state, event)","plane":"ops","facts":{}}},"types":{"WorkItem.Role":{"enum":["Owner","Opus","Sol","Chat","Free","Jev","Slm","Ci"]},"WorkItem.Actor":{"ctors":{"Actor":{"id":"Nat","role":"WorkItem.Role"}}},"WorkItem.Receipt":{"ctors":{"Receipt":{"sha":"Nat","pass":"Bool"}}},"WorkItem.Avail":{"enum":["DeepWork","LowEnergy","Off"]},"WorkItem.Item":{"ctors":{"Proposed":{},"Claimed":{"au":"WorkItem.Actor"},"Implementing":{"au":"WorkItem.Actor","hd":"Nat"},"Verifying":{"au":"WorkItem.Actor","hd":"Nat"},"DraftPR":{"au":"WorkItem.Actor","hd":"Nat"},"Integrated":{"au":"WorkItem.Actor","hd":"Nat","ig":"Nat"},"Deployed":{"au":"WorkItem.Actor","hd":"Nat","ig":"Nat","dp":"Nat"},"Accepted":{"au":"WorkItem.Actor","hd":"Nat","ig":"Nat","ap":"WorkItem.Actor"},"Merged":{"au":"WorkItem.Actor","hd":"Nat","ig":"Nat","ap":"WorkItem.Actor"},"Blocked":{"au":"WorkItem.Actor","hd":"Nat"},"Interrupted":{"au":"WorkItem.Actor","hd":"Nat"},"Abandoned":{}}},"WorkItem.Ev":{"ctors":{"Claim":{"a":"WorkItem.Actor"},"Start":{"a":"WorkItem.Actor"},"Push":{"a":"WorkItem.Actor","sha":"Nat"},"Submit":{"a":"WorkItem.Actor"},"Verify":{"a":"WorkItem.Actor","r":"WorkItem.Receipt"},"Integrate":{"a":"WorkItem.Actor","ish":"Nat","r":"WorkItem.Receipt"},"Deploy":{"a":"WorkItem.Actor","served":"Nat"},"Observe":{"served":"Nat"},"Accept":{"a":"WorkItem.Actor"},"Merge":{"a":"WorkItem.Actor"},"Block":{"a":"WorkItem.Actor"},"Unblock":{"a":"WorkItem.Actor"},"Interrupt":{},"Resume":{"a":"WorkItem.Actor"},"Abandon":{"a":"WorkItem.Actor"}}},"WorkerSupervision.Host":{"enum":["Groot","Mbp","Phone"]},"WorkerSupervision.Load":{"enum":["Light","Heavy"]},"WorkerSupervision.Exc":{"enum":["NoExc","Gpu","Toolchain"]},"WorkerSupervision.W":{"ctors":{"W":{"id":"Nat","wt":"Nat","load":"WorkerSupervision.Load","exc":"WorkerSupervision.Exc"}}},"WorkerSupervision.St":{"ctors":{"Dispatched":{"w":"WorkerSupervision.W"},"Running":{"w":"WorkerSupervision.W","h":"WorkerSupervision.Host","hb":"Nat","bg":"Nat"},"Stalled":{"w":"WorkerSupervision.W","h":"WorkerSupervision.Host","hb":"Nat","bg":"Nat"},"Interrupted":{"w":"WorkerSupervision.W","at":"Nat","bg":"Nat"},"Overdue":{"w":"WorkerSupervision.W","at":"Nat","bg":"Nat"},"Completed":{"w":"WorkerSupervision.W","bg":"Nat"},"Resumed":{"w":"WorkerSupervision.W","by":"Nat","bg":"Nat"},"Abandoned":{"w":"WorkerSupervision.W"},"Integrated":{"w":"WorkerSupervision.W"}}},"WorkerSupervision.Ev":{"ctors":{"Start":{"h":"WorkerSupervision.Host","t":"Nat"},"Beat":{"t":"Nat"},"Spawn":{},"Reap":{},"Tick":{"now":"Nat"},"Finish":{},"Interrupt":{"t":"Nat"},"Resume":{"by":"Nat","log":"Bool"},"Abandon":{},"Integrate":{}}},"WorkerSupervision.Lease":{"ctors":{"Free":{},"Held":{"o":"Nat"}}},"WorkerSupervision.LEv":{"ctors":{"Acquire":{"a":"Nat"},"Release":{"a":"Nat"},"Reclaim":{"a":"Nat","dead":"Bool"}}},"WorkerSupervision.Fg":{"ctors":{"Unknown":{},"Seen":{"app":"Nat"}}},"WorkerSupervision.Device":{"ctors":{"Dev":{"lk":"WorkerSupervision.Lease","fg":"WorkerSupervision.Fg"}}},"WorkerSupervision.PEv":{"ctors":{"Lock":{"a":"Nat"},"Unlock":{"a":"Nat"},"Peek":{"app":"Nat"},"Install":{"a":"Nat"},"Input":{"a":"Nat","app":"Nat"}}},"WorkerSupervision.Eff":{"ctors":{"NoEff":{},"Installed":{"a":"Nat"},"Typed":{"a":"Nat","app":"Nat"}}},"IntegrationOwner.St":{"ctors":{"Branch":{},"DraftPR":{},"Queued":{},"OnIntegrationBranch":{},"Deployed":{},"OwnerAccepted":{},"Merged":{},"Parked":{},"Conflicted":{}}},"IntegrationOwner.Ev":{"ctors":{"Draft":{},"Queue":{},"Integrate":{"lease":"Bool","stack":"Bool","independent":"Bool"},"Deploy":{"equal":"Bool"},"Accept":{"owner":"Bool"},"Merge":{},"Park":{"reason":"Bool","future":"Bool"},"Conflict":{},"Resume":{},"Observe":{"equal":"Bool"},"Expire":{"expired":"Bool"}}},"Ops.Cls":{"enum":["CTest","CMutation","CTypecheck","CGradle","CBundle","CEval","CShot","CGpu","CBend","CLean","CService","CAgent","CTiny"]},"Ops.GitOp":{"enum":["GEdit","GCommit","GCheckout","GStash","GMerge","GMergeFF","GRollback"]},"Ops.Vis":{"enum":["VPublic","VPrivate","VUnknown"]},"Ops.Req":{"ctors":{"Req":{"clean":"Bool","ff":"Bool","gated":"Bool","receipt":"Bool","call":"Bool","idle":"Bool"}}},"Ops.PAct":{"ctors":{"PTap":{"intent":"Bool","fg":"Bool"},"PInstall":{"chain":"Bool"},"PRestart":{"chain":"Bool"}}},"OpsLayer.GSt":{"ctors":{"GIdle":{},"GAdmitted":{},"GWaiting":{},"GRefused":{},"GRolledBack":{}}},"OpsLayer.GEv":{"ctors":{"GPlace":{"c":"Ops.Cls","mbp":"Bool","phone":"Bool"},"GGit":{"served":"Bool","op":"Ops.GitOp","txn":"Bool"},"GRoll":{"q":"Ops.Req","check":"Bool"},"GPush":{"private":"Bool","vis":"Ops.Vis"},"GPhone":{"a":"Ops.PAct","call":"Bool"},"GRoute":{"cancelled":"Bool","sol":"Bool","design":"Bool"}}},"Ops.NSt":{"ctors":{"NHealthy":{},"NBad":{"since":"Nat"},"NNotified":{"since":"Nat"}}},"Ops.NEv":{"ctors":{"NProbe":{"ok":"Bool","now":"Nat"}}},"Ops.RSt":{"ctors":{"RActive":{"gw":"Nat"},"RInterrupted":{"gw":"Nat"},"RFailed":{},"RDone":{},"RResumed":{},"RReported":{}}},"Ops.REv":{"ctors":{"GwRestart":{"gw":"Nat"},"RunError":{},"RunDone":{},"ResumeRun":{"session":"Bool"},"ReportRun":{}}}},"states":{"work-item":[{"id":0,"tag":"Proposed","machine":"work-item","owner":"PROPOSED","title":"Proposed","summary":"Someone wrote down a piece of work. Nobody owns it yet.","point":{"x":24,"y":34}},{"id":1,"tag":"Claimed","machine":"work-item","owner":"CLAIMED","title":"Claimed","summary":"A coding lane (Opus or Sol only) took it. That actor becomes the author.","point":{"x":244,"y":34}},{"id":2,"tag":"Implementing","machine":"work-item","owner":"IMPLEMENTING","title":"Implementing","summary":"The author is writing code and pushing commits; the head SHA moves.","point":{"x":464,"y":34}},{"id":3,"tag":"Verifying","machine":"work-item","owner":"VERIFYING","title":"Verifying","summary":"The author submitted. A CI actor who is not the author checks a receipt bound to this exact head.","point":{"x":684,"y":34}},{"id":4,"tag":"DraftPR","machine":"work-item","owner":"DRAFT PR","title":"DraftPR","summary":"A passing receipt for the head opened a draft PR.","point":{"x":684,"y":228}},{"id":5,"tag":"Integrated","machine":"work-item","owner":"INTEGRATED","title":"Integrated","summary":"Ci or Opus (not the author) landed it on an integration branch with a passing receipt for that head.","point":{"x":684,"y":422}},{"id":6,"tag":"Deployed","machine":"work-item","owner":"DEPLOYED · NEEDS KEVIN","title":"Deployed","summary":"The running service serves exactly the integrated head. The item now waits in the batched needs-Kevin queue.","point":{"x":464,"y":422}},{"id":7,"tag":"Accepted","machine":"work-item","owner":"OWNER ACCEPTED","title":"OwnerAccepted","summary":"Kevin (the owner, never the author) looked at the deployed result and said yes.","point":{"x":244,"y":422}},{"id":8,"tag":"Merged","machine":"work-item","owner":"MERGED","title":"Merged","summary":"Ci or the owner merged to the default branch, carrying the owner's acceptance.","point":{"x":24,"y":422},"terminal":true},{"id":9,"tag":"Blocked","machine":"work-item","owner":"BLOCKED","title":"Blocked","summary":"Stuck on something outside the work. Only the owner or Opus unblocks or abandons.","point":{"x":464,"y":228}},{"id":10,"tag":"Interrupted","machine":"work-item","owner":"INTERRUPTED","title":"Interrupted","summary":"The worker died or was stopped. Its pushed head is kept; only Resume or an explicit Abandon moves it.","point":{"x":244,"y":228}},{"id":11,"tag":"Abandoned","machine":"work-item","owner":"ABANDONED","title":"Abandoned","summary":"An explicit decision by the owner or Opus to drop the work.","point":{"x":24,"y":228},"terminal":true}],"worker":[{"id":0,"tag":"Dispatched","machine":"worker","owner":"DISPATCHED","title":"Dispatched","summary":"A delegated worker exists but has not started on a host yet.","point":{"x":24,"y":34}},{"id":1,"tag":"Running","machine":"worker","owner":"RUNNING","title":"Running","summary":"Working on a host and sending heartbeats.","point":{"x":244,"y":34}},{"id":2,"tag":"Stalled","machine":"worker","owner":"STALLED","title":"Stalled","summary":"No heartbeat for longer than the limit. One more limit of silence and it counts as interrupted.","point":{"x":464,"y":34}},{"id":3,"tag":"Interrupted","machine":"worker","owner":"INTERRUPTED","title":"Interrupted","summary":"The worker stopped mid-task. A successor must resume it from its log, or someone abandons it explicitly.","point":{"x":244,"y":228}},{"id":4,"tag":"Overdue","machine":"worker","owner":"OVERDUE · NEEDS KEVIN","title":"Overdue","summary":"Interrupted for longer than the limit with no decision. It sits in the needs-Kevin queue instead of vanishing.","point":{"x":464,"y":228}},{"id":5,"tag":"Completed","machine":"worker","owner":"COMPLETED","title":"Completed","summary":"Finished. Its background processes must be reaped before it can be integrated or dropped.","point":{"x":684,"y":34}},{"id":6,"tag":"Resumed","machine":"worker","owner":"RESUMED","title":"Resumed","summary":"A successor read the log and took the work (and its background processes) over.","point":{"x":354,"y":422},"terminal":true},{"id":7,"tag":"Abandoned","machine":"worker","owner":"ABANDONED","title":"Abandoned","summary":"Dropped on purpose, with no background process left running.","point":{"x":24,"y":228},"terminal":true},{"id":8,"tag":"Integrated","machine":"worker","owner":"INTEGRATED","title":"Integrated","summary":"Its result landed, with no background process left running.","point":{"x":684,"y":228},"terminal":true}],"lease":[{"id":0,"tag":"Free","machine":"lease","owner":"LEASE · FREE","title":"Lease free","summary":"No session owns this worktree/branch (or the S25 install lock).","point":{"x":24,"y":34}},{"id":1,"tag":"Held","machine":"lease","owner":"LEASE · HELD","title":"Lease held","summary":"Exactly one session owns it. Only the holder writes or releases; a takeover needs Reclaim with evidence the holder is dead.","point":{"x":244,"y":34}}],"device":[{"id":0,"tag":"free-unknown","machine":"device","owner":"S25 · LOCK FREE","title":"Foreground unknown","summary":"Nobody holds the install lock and nobody has looked at the screen since the last input.","point":{"x":24,"y":228}},{"id":1,"tag":"free-seen","machine":"device","owner":"S25 · LOCK FREE","title":"Foreground seen","summary":"Someone just looked: the foreground app is known, so one input may go to that app.","point":{"x":244,"y":228}},{"id":2,"tag":"held-unknown","machine":"device","owner":"S25 · LOCK HELD","title":"Foreground unknown","summary":"A worker holds the install lock; the screen has not been looked at since the last input.","point":{"x":24,"y":422}},{"id":3,"tag":"held-seen","machine":"device","owner":"S25 · LOCK HELD","title":"Foreground seen","summary":"Lock held and the foreground app is known.","point":{"x":244,"y":422}}],"integration":[{"id":0,"tag":"Branch","machine":"integration","owner":"Integration owner","title":"Branch","summary":"Loop 3: Branch","point":{"x":24,"y":34}},{"id":1,"tag":"DraftPR","machine":"integration","owner":"Integration owner","title":"DraftPR","summary":"Loop 3: DraftPR","point":{"x":244,"y":34}},{"id":2,"tag":"Queued","machine":"integration","owner":"Integration owner","title":"Queued","summary":"Loop 3: Queued","point":{"x":464,"y":34}},{"id":3,"tag":"OnIntegrationBranch","machine":"integration","owner":"Integration owner","title":"OnIntegrationBranch","summary":"Loop 3: OnIntegrationBranch","point":{"x":684,"y":34}},{"id":4,"tag":"Deployed","machine":"integration","owner":"Integration owner","title":"Deployed","summary":"Exact running/build SHA equals integration head; checkout HEAD alone is insufficient.","point":{"x":684,"y":228}},{"id":5,"tag":"OwnerAccepted","machine":"integration","owner":"Kevin","title":"OwnerAccepted","summary":"Loop 3: OwnerAccepted","point":{"x":464,"y":228}},{"id":6,"tag":"Merged","machine":"integration","owner":"Integration owner","title":"Merged","summary":"Loop 3: Merged","point":{"x":244,"y":228},"terminal":true},{"id":7,"tag":"Parked","machine":"integration","owner":"Integration owner","title":"Parked","summary":"Explicit reason + future expiry in the head-bound decision record. Expiry requeues.","point":{"x":24,"y":422}},{"id":8,"tag":"Conflicted","machine":"integration","owner":"Integration owner","title":"Conflicted","summary":"Repair in isolation, re-test, then requeue.","point":{"x":244,"y":422}}],"ops-gates":[{"id":0,"tag":"GIdle","machine":"ops-gates","owner":"GATE","title":"Action proposed","summary":"An agent is about to run a job, touch a served worktree, roll out, push, touch the owner's phone or route a role.","point":{"x":24,"y":34}},{"id":1,"tag":"GAdmitted","machine":"ops-gates","owner":"GATE","title":"Admitted","summary":"Every precondition held; the action may run (a pass is not an authorization).","point":{"x":244,"y":34}},{"id":2,"tag":"GWaiting","machine":"ops-gates","owner":"GATE","title":"Waits / deferred","summary":"O1: no worker lane has room, so the job waits (never groot). O3: owner call live or service busy, so the rollout is pending.","point":{"x":464,"y":34}},{"id":3,"tag":"GRefused","machine":"ops-gates","owner":"GATE","title":"Refused","summary":"A known-bad action: heavy job on groot, edit in a served worktree, private push to a public remote, phone tap without intent, Grok/Sol-design route.","point":{"x":244,"y":150}},{"id":4,"tag":"GRolledBack","machine":"ops-gates","owner":"GATE","title":"Rolled back","summary":"The rollout ran but the device launch check failed: the served worktree went back to the revision it replaced and the service restarted.","point":{"x":464,"y":150}}],"node-health":[{"id":0,"tag":"NHealthy","machine":"node-health","owner":"O8","title":"Healthy","summary":"The worker node passes its health probe.","point":{"x":24,"y":290}},{"id":1,"tag":"NBad","machine":"node-health","owner":"O8","title":"Unhealthy","summary":"Failing probes; the clock started at the first one. No notification yet.","point":{"x":244,"y":290}},{"id":2,"tag":"NNotified","machine":"node-health","owner":"O8","title":"Owner notified","summary":"Past 30 min the next bad probe sent exactly one notification; nothing more until the node recovers.","point":{"x":464,"y":290}}],"gateway-run":[{"id":0,"tag":"RActive","machine":"gateway-run","owner":"O9","title":"Active","summary":"A headless sol run hosted by the gateway.","point":{"x":24,"y":430}},{"id":1,"tag":"RInterrupted","machine":"gateway-run","owner":"O9","title":"Interrupted","summary":"The gateway restarted under it: recorded with a resume command, never silently Failed.","point":{"x":244,"y":430}},{"id":2,"tag":"RFailed","machine":"gateway-run","owner":"O9","title":"Failed","summary":"The run itself failed (its own error), not a gateway restart.","point":{"x":24,"y":556},"terminal":true},{"id":3,"tag":"RDone","machine":"gateway-run","owner":"O9","title":"Done","summary":"The run finished and wrote its report.","point":{"x":244,"y":556},"terminal":true},{"id":4,"tag":"RResumed","machine":"gateway-run","owner":"O9","title":"Resumed","summary":"Continued from its own session/run directory.","point":{"x":464,"y":430},"terminal":true},{"id":5,"tag":"RReported","machine":"gateway-run","owner":"O9","title":"Reported","summary":"Not resumed; reported to the owner instead.","point":{"x":684,"y":430},"terminal":true}]},"laws":[{"id":"L1","loop":"work-item","name":"No merge without owner acceptance","text":"Merged is reachable only from OwnerAccepted, and that acceptance came from the owner, who is not the author.","prevents":"Agents (which act under Kevin's GitHub account) merging to main before Kevin has seen the deployed result.","incidents":{"count":6,"label":"PRs merged with no recorded owner acceptance of a deployed head","source":"replay-20261021 law1:merged_without_owner_acceptance"}},{"id":"L2","loop":"work-item","name":"No self-approval","text":"Verify (Ci), Integrate (Ci or Opus) and Accept (owner) are each passed only by an actor of the right role who is not the author.","prevents":"An agent grading or landing its own work.","incidents":{"count":5,"label":"integrations by the author's own account (indeterminate: agents share the owner's GitHub identity)","source":"replay-20261021 law2:self_integrated"}},{"id":"L3","loop":"work-item","name":"Receipt bound to the head","text":"A draft PR needs a passing test receipt for exactly the head SHA; integration needs one for the integration head.","prevents":"\"Tests passed\" on an older commit being used to land a newer one.","incidents":{"count":39,"label":"integrated while the head had no passing receipt","source":"replay-20261021 law3:integrated_without_head_receipt"}},{"id":"L4","loop":"work-item","name":"Deployed == integrated","text":"Deploy succeeds only when the service serves exactly the integrated head; observing any other head takes \"deployed\" away.","prevents":"The stale-service bug: a service quietly running an old or diverged build.","incidents":{"count":6,"label":"services stale (1), diverged (1) or missing merged commits (4)","source":"replay-20261021 law4:*"}},{"id":"L5","loop":"work-item","name":"Interrupted is never dropped","text":"Interrupted leaves only by Resume (a coder takes the pushed head over) or an explicit Abandon by the owner or Opus.","prevents":"Half-done work silently disappearing when a worker dies.","incidents":{"count":13,"label":"interrupted items with no resume, PR or abandon decision","source":"replay-20261021 law5:interrupted_dropped"}},{"id":"L6","loop":"work-item","name":"Free models never implement","text":"Only Opus or Sol can claim or resume work; free models, Jev, SLMs and chat apps pick, rank and advise.","prevents":"Code written by a lane the owner ruled out for code.","incidents":{"count":0,"label":"no free-model claims seen; the model makes them unreachable","source":"fsm-work-item-v0 proof"}},{"id":"L7","loop":"work-item","name":"Owner is a batched queue, not a blocker","text":"While Kevin is Off, an owner action is held and the item waits in the needs-Kevin queue; everything else keeps moving.","prevents":"Pinging Kevin outside a deep-work block, or one owner decision freezing other work.","incidents":{"count":3,"label":"items in the needs-Kevin queue at report time (availability: off)","source":"replay-20261021 needs_kevin"}},{"id":"W1","loop":"worker","name":"One owner per worktree","text":"A held lease passes on only by Reclaim with evidence the holder is dead; only the holder writes or releases.","prevents":"Two sessions editing the same worktree or branch at once.","incidents":{"count":419,"label":"writes by a second session while another held the worktree (19 worktrees)","source":"supervise-20261021 L1:worktree_two_owners"}},{"id":"W2","loop":"worker","name":"Resume from the log, or decide, within 2 h","text":"An interrupted worker is resumed from its log or explicitly abandoned; past the limit it turns Overdue (needs Kevin).","prevents":"Successors restarting blind, and interrupted workers rotting unnoticed.","incidents":{"count":36,"label":"26 interrupted past the 2 h limit + 10 resumed without reading the log","source":"supervise-20261021 L2:*"}},{"id":"W3","loop":"worker","name":"Reap or adopt background processes","text":"A worker reaches Abandoned or Integrated only with zero background processes; Resume hands them to the successor.","prevents":"Orphaned servers and jobs eating groot's memory after their owner died.","incidents":{"count":1,"label":"orphaned process still alive (plus 21 children reaped by Hermes, result lost)","source":"supervise-20261021 L3:*"}},{"id":"W4","loop":"worker","name":"Heavy work off groot","text":"Heavy work starts on groot only with a declared GPU or toolchain exception; otherwise it runs on the MBP or a phone.","prevents":"Builds starving the memory-tight desktop and killing other workers.","incidents":{"count":1695,"label":"heavy commands on groot with no exception (97 since the fleet came online; 1,310 excepted)","source":"supervise-20261021 L4:heavy_on_groot"}},{"id":"W5","loop":"worker","name":"Phone installs serialized","text":"Only the holder of the S25 install lock may install.","prevents":"Two agents installing builds over each other on the owner's phone.","incidents":{"count":7,"label":"of 17 S25 installs ran outside the lock","source":"supervise-20261021 L5:install_without_lock"}},{"id":"W6","loop":"worker","name":"Look before you tap","text":"Input goes only to the app last seen in the foreground, and each input spends that look.","prevents":"Taps landing in whatever app Kevin happens to have open.","incidents":{"count":11,"label":"of 23 S25 inputs sent with no foreground check","source":"supervise-20261021 L6:input_without_foreground_check"}},{"id":"I1","loop":"3","name":"Draft deadline","text":"Within 24 h: contained or explicitly parked, with reason and expiry. Unknown branch is an evidence gap, not verified non-containment.","prevents":"Within 24 h: contained or explicitly parked, with reason and expiry. Unknown branch is an evidence gap, not verified non-containment.","incidents":{"count":53,"label":"findings / evidence gaps (not all proven violations)","source":"integration-20261021.json"}},{"id":"I2","loop":"3","name":"Runtime equals integration","text":"Exact served/build SHA must equal integration head. Stale checkouts and unattested runtimes stay red.","prevents":"Exact served/build SHA must equal integration head. Stale checkouts and unattested runtimes stay red.","incidents":{"count":7,"label":"findings / evidence gaps (not all proven violations)","source":"integration-20261021.json"}},{"id":"I3","loop":"3","name":"One leased integration owner","text":"One unexpired per-repository lease. An active holder cannot be displaced.","prevents":"One unexpired per-repository lease. An active holder cannot be displaced.","incidents":{"count":8,"label":"findings / evidence gaps (not all proven violations)","source":"integration-20261021.json"}},{"id":"I4","loop":"3","name":"Consistent stacked chains","text":"A child's recorded base must contain its parent's current head.","prevents":"A child's recorded base must contain its parent's current head.","incidents":{"count":11,"label":"findings / evidence gaps (not all proven violations)","source":"integration-20261021.json"}},{"id":"I5","loop":"3","name":"Owner accepts before merge","text":"Only OwnerAccepted reaches Merged. Agents never approve their own work.","prevents":"Only OwnerAccepted reaches Merged. Agents never approve their own work.","incidents":{"count":0,"label":"findings / evidence gaps (not all proven violations)","source":"integration-20261021.json"}},{"id":"O1","loop":"ops","name":"Compute placement","text":"Heavy job classes are admitted only on a non-groot lane; with no room they wait, never groot.","prevents":"groot running every bundle and test from 10:30 while the MBP sat idle","incidents":{"count":196,"label":"local heavy commands on groot 10:30-16:00 (state.db replay)","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O2","loop":"ops","name":"Served worktree","text":"No edit/commit/checkout/stash/merge in a worktree serving a live service, except merge --ff-only + idle restart in one transaction.","prevents":"in-place edits under the served Dash (HTTP 500 on the phone, 11:31)","incidents":{"count":35,"label":"served-worktree reflog entries 09:59-15:56, none in a transaction","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O3","loop":"ops","name":"Device rollout gate","text":"Candidate from a non-served worktree, launch check on the real runtime after restart with rollback, review receipt when gated.","prevents":"fast-motion promoted on a bundle readback, crashed the phone at launch (15:51)","incidents":{"count":1,"label":"rollout without a device launch check","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O4","loop":"ops","name":"Privacy boundary","text":"Private-marked artifacts never go to a public remote.","prevents":"taste-data (private) leaking into the public taste-skill fork","incidents":{"count":0,"label":"no leak found; boundary was unenforced","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O5","loop":"ops","name":"Owner phone touch","text":"UI input needs an owner phone request and the expected foreground app; no call-chain install during a live call.","prevents":"the voice agent tapping 'Phone' while only checking a relay (16:25)","incidents":{"count":3,"label":"phone_do calls without a phone request (1 landed)","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O6","loop":"ops","name":"Accessibility preservation","text":"Enabled accessibility services after an install ⊇ before, unless the owner removed one.","prevents":"every reinstall turning off z0live in-app control","incidents":{"count":1,"label":"recurring on every reinstall","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O7","loop":"ops","name":"Provider routing","text":"No role routes to a cancelled provider; design roles never route to Sol.","prevents":"Grok roles after the xai cancellation; Sol design rework","incidents":{"count":11,"label":"current config findings (hourly check)","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O8","loop":"ops","name":"Node health notifies once","text":"A worker node unhealthy >30 min emits exactly one owner notification.","prevents":"S22+ offline since 01:47 with hundreds of silent strikes","incidents":{"count":1,"label":"node silent all day (0 notifications)","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}},{"id":"O9","loop":"ops","name":"Gateway restart interrupts","text":"Dependent runs become Interrupted with resume commands, never silently Failed.","prevents":"six sol runs cut off at 11:58, noticed 26 min later","incidents":{"count":6,"label":"runs cut off by the 11:58 Hermes update","source":"kvnloo/z0intelligence tests/fixtures/ops_tapes"}}],"guards":[{"machine":"work-item","from":"Proposed","event":"Claim","laws":["L6"],"text":"Only Opus or Sol may claim; free models, Jev, SLMs and chat apps never implement."},{"machine":"work-item","from":"*","event":"Abandon","laws":["L5"],"text":"Only the owner or the Opus orchestrator may abandon."},{"machine":"work-item","from":"Claimed","event":"Start","laws":["L2"],"text":"Only the claimant (author) starts."},{"machine":"work-item","from":"Implementing","event":"Push","laws":["L2"],"text":"Only the author pushes."},{"machine":"work-item","from":"Implementing","event":"Submit","laws":["L2"],"text":"Only the author submits."},{"machine":"work-item","from":"Verifying","event":"Verify","laws":["L2","L3"],"text":"A Ci actor who is not the author decides; only a passing receipt for exactly this head opens the draft PR."},{"machine":"work-item","from":"DraftPR","event":"Integrate","laws":["L2","L3"],"text":"Ci or Opus, not the author, with a passing receipt bound to the integration head."},{"machine":"work-item","from":"Integrated","event":"Deploy","laws":["L4"],"text":"An operator deploys, and the served head must equal the integrated head."},{"machine":"work-item","from":"Deployed","event":"Observe","laws":["L4"],"text":"A service seen serving any other head drops back to Integrated.","kind":"observation"},{"machine":"work-item","from":"Deployed","event":"Accept","laws":["L1","L2","L7"],"text":"Only the owner, who is not the author, accepts."},{"machine":"work-item","from":"Accepted","event":"Merge","laws":["L1"],"text":"Ci or the owner merges after acceptance."},{"machine":"work-item","from":"*","event":"Merge","laws":["L1"],"text":"Merge is possible only from OwnerAccepted."},{"machine":"work-item","from":"*","event":"Accept","laws":["L1"],"text":"Acceptance is possible only for a deployed result."},{"machine":"work-item","from":"*","event":"Integrate","laws":["L3"],"text":"Integration is possible only from a draft PR that passed verification."},{"machine":"work-item","from":"Blocked","event":"Unblock","laws":[],"text":"Only the owner or Opus unblocks."},{"machine":"work-item","from":"Interrupted","event":"Resume","laws":["L5","L6"],"text":"A coder (Opus or Sol) resumes, keeping the pushed head."},{"machine":"worker","from":"Dispatched","event":"Start","laws":["W4"],"text":"Heavy work starts on groot only with a declared GPU or toolchain exception."},{"machine":"worker","from":"Running","event":"Tick","laws":["W2"],"text":"Heartbeat clock: still within the limit.","kind":"clock"},{"machine":"worker","from":"Stalled","event":"Tick","laws":["W2"],"text":"Heartbeat clock: not yet two limits of silence.","kind":"clock"},{"machine":"worker","from":"Interrupted","event":"Tick","laws":["W2"],"text":"Decision clock: still within the limit.","kind":"clock"},{"machine":"worker","from":"Interrupted","event":"Resume","laws":["W2"],"text":"A successor may resume only from the worker's log."},{"machine":"worker","from":"Overdue","event":"Resume","laws":["W2"],"text":"A successor may resume only from the worker's log."},{"machine":"worker","from":"*","event":"Abandon","laws":["W3"],"text":"Abandon only once every background process is reaped."},{"machine":"worker","from":"Completed","event":"Integrate","laws":["W3"],"text":"Integrate only once every background process is reaped."},{"machine":"lease","from":"Held","event":"Acquire","laws":["W1"],"text":"A held lease cannot be taken; only Reclaim with evidence the holder is dead."},{"machine":"lease","from":"Held","event":"Release","laws":["W1"],"text":"Only the holder releases."},{"machine":"lease","from":"Held","event":"Reclaim","laws":["W1"],"text":"Reclaim needs evidence the holder is dead."},{"machine":"device","from":"*","event":"Install","laws":["W5"],"text":"Only the install-lock holder installs.","acceptance":"effect"},{"machine":"device","from":"*","event":"Input","laws":["W6"],"text":"Input only into the app last seen in the foreground; each input spends the look.","acceptance":"effect"},{"machine":"device","from":"*","event":"Unlock","laws":["W1","W5"],"text":"Only the holder releases the install lock."},{"machine":"device","from":"*","event":"Lock","laws":["W5"],"text":"The install lock is already held by someone else."},{"machine":"integration","from":"*","event":"Integrate","laws":["I3","I4"],"text":"A held lease, consistent stack and independent review are required."},{"machine":"integration","from":"*","event":"Deploy","laws":["I2"],"text":"Need exact runtime equality evidence, not checkout HEAD."},{"machine":"integration","from":"*","event":"Accept","laws":["I5"],"text":"Only an independently identified owner can accept."},{"machine":"integration","from":"*","event":"Merge","laws":["I5"],"text":"Only OwnerAccepted can merge."},{"machine":"integration","from":"*","event":"Park","laws":["I1"],"text":"Need explicit reason and a future expiry."},{"machine":"integration","from":"*","event":"Expire","laws":["I1"],"text":"An expired parking decision returns to the queue.","kind":"observation"},{"machine":"integration","from":"*","event":"Observe","laws":["I2"],"text":"Drift revokes deployment and owner acceptance.","kind":"observation"},{"machine":"ops-gates","from":"*","event":"GPlace","laws":["O1"],"text":"Test, mutation, typecheck, gradle, bundle, eval and screenshot jobs run on mbp or a phone; with no room they wait. groot runs gpu, bend, lean, services, agents and tiny jobs only."},{"machine":"ops-gates","from":"*","event":"GGit","laws":["O2"],"text":"A served worktree takes no edit, commit, checkout, stash or merge, except merge --ff-only (and its rollback) inside z0-guard rollout."},{"machine":"ops-gates","from":"*","event":"GRoll","laws":["O2","O3"],"text":"Candidate from a clean non-served worktree, fast-forward into an idle service, review receipt if gated, device launch check after restart (never during an owner call), automatic rollback."},{"machine":"ops-gates","from":"*","event":"GPush","laws":["O4"],"text":"Private-marked content goes only to a remote known to be private; unknown visibility fails closed."},{"machine":"ops-gates","from":"*","event":"GPhone","laws":["O5"],"text":"A tap needs an explicit owner phone request and the expected app in front; no call-chain install/restart during a live z0live call."},{"machine":"ops-gates","from":"*","event":"GRoute","laws":["O7"],"text":"No role routes to a cancelled provider (xai/grok); design roles never route to Sol."},{"machine":"node-health","from":"NBad","event":"NProbe","laws":["O8"],"kind":"clock","text":"Still within 30 min: no notification yet."},{"machine":"node-health","from":"NNotified","event":"NProbe","laws":["O8"],"kind":"clock","text":"Already notified for this episode: stays quiet until the node is healthy again."},{"machine":"gateway-run","from":"RActive","event":"GwRestart","laws":["O9"],"text":"Only a restart of this run's own gateway interrupts it, and it becomes Interrupted, never Failed."},{"machine":"gateway-run","from":"RInterrupted","event":"ResumeRun","laws":["O9"],"text":"Resume counts only from the run's own session."},{"machine":"gateway-run","from":"RInterrupted","event":"RunError","laws":["O9"],"text":"An interrupted run is never turned into Failed."},{"machine":"gateway-run","from":"RInterrupted","event":"RunDone","laws":["O9"],"text":"An interrupted run is never silently counted as done."},{"machine":"node-health","from":"NHealthy","event":"NProbe","laws":["O8"],"kind":"observation","text":"Healthy probe: nothing to report."}],"planes":[{"id":"work-item","title":"Loop 1 · Work item","owner":"PROPOSED → MERGED","color":"#386eb1","machines":["work-item"],"summary":"One piece of work from proposal to merge. Draft PR kvnloo/z0intelligence#183.","width":880,"height":505},{"id":"worker","title":"Loop 2 · Worker","owner":"DISPATCHED → RESUMED / INTEGRATED","color":"#31836a","machines":["worker"],"summary":"One delegated agent from dispatch to an honest ending. Draft PR kvnloo/z0intelligence#184.","width":880,"height":505},{"id":"shared","title":"Loop 2 · Shared resources","owner":"LEASE · S25","color":"#a4772e","machines":["lease","device"],"summary":"The worktree lease (also the S25 install lock) and the owner's phone.","width":880,"height":505,"lawCards":[{"law":"W1","point":{"x":464,"y":34}},{"law":"W5","point":{"x":684,"y":34}},{"law":"W6","point":{"x":464,"y":228}},{"law":"W4","point":{"x":684,"y":228}},{"law":"W3","point":{"x":464,"y":422}},{"law":"W2","point":{"x":684,"y":422}}]},{"id":"integration","title":"Loop 3 · Integration owner","owner":"Independent integration agent · Kevin accepts","color":"#d7a96a","machines":["integration"],"summary":"Keep draft work on an integration branch; deploy its exact head; batch owner acceptance. Unknown runtime SHA is not green.","width":894,"height":530},{"id":"ops","title":"Ops · operating rules O1–O9","owner":"z0-guard gates · Bend-proven","color":"#8a5cc2","machines":["ops-gates","node-health","gateway-run"],"summary":"Rules that lived in markdown, now Bend laws with deterministic gates: placement, served worktrees, rollouts, privacy, the owner's phone, accessibility, routing, node health, gateway restarts. Draft PR kvnloo/z0intelligence#192.","width":894,"height":660}],"nodeSize":{"width":172,"height":74},"curves":{"work-item":{"Blocked>Abandoned":[[550,362],[110,362]],"Verifying>Interrupted":-30},"worker":{"Running>Completed":-22,"Overdue>Abandoned":[[550,340],[150,340]],"Completed>Abandoned":[[870,71],[870,390],[70,390]]},"lease":{},"device":{},"integration":{},"ops-gates":{},"node-health":{},"gateway-run":{}},"roles":[{"id":"Owner","who":"Kevin","note":"Taste, credentials, physical world, irreversible approvals. Attention is the bottleneck: one batched needs-Kevin queue."},{"id":"Opus","who":"Claude Opus lane","note":"Design, verification, hard code, orchestration. May claim, integrate, unblock, abandon."},{"id":"Sol","who":"Sol via pi/SoL-Pi or Codex","note":"Bulk well-specified coding. May claim and resume."},{"id":"Chat","who":"ChatGPT app, Grok, Muse","note":"Advice and specs; no sandbox, no origin actions."},{"id":"Free","who":"Free models","note":"Scans, triage, summaries. Never code (owner rule, L6)."},{"id":"Jev","who":"Jev","note":"Fast chooser among prevalidated options; never writes."},{"id":"Slm","who":"Shadow network","note":"Shadow-only until promoted; never writes."},{"id":"Ci","who":"Deterministic code","note":"CI, tests, service-branch checks, replay. Verifies and integrates; never the author."}],"explainer":{"intro":"Three small Bend control-plane loops, drawn as layers. Every guard probe runs the same compiled Bend model.","loops":["Loop 1 follows one piece of work: Proposed → Claimed (Opus or Sol only) → Implementing → Verifying (CI, not the author, checks a receipt for that exact commit) → Draft PR → Integrated → Deployed (the service must run exactly that commit) → OwnerAccepted (only Kevin) → Merged. Blocked, Interrupted and Abandoned are the side exits.","Loop 2 follows one delegated agent: Dispatched → Running (heartbeats) → Completed → Integrated. If it goes quiet it Stalls, then counts as Interrupted; a successor must resume from its log, or someone abandons it once its background processes are reaped. Past 2 h with no decision it turns Overdue and lands in Kevin's queue instead of vanishing. Beside it: one owner per worktree (the lease) and the S25 rules (install lock, look before you tap).","Loop 3 follows integration ownership: Branch → DraftPR → Queued → OnIntegrationBranch → Deployed → OwnerAccepted → Merged. Parked needs a reason and expiry. Conflicted needs repair. Snapshot tapes are evidence-backed what-if probes, not historical action logs.","The ops plane holds the owner's operating rules O1–O9 from 21 Oct. Each gate (job placement, served worktree, rollout, push, phone, routing) is a Bend decision function; the state is just its last verdict. Next to it, node health notifies exactly once per outage (O8) and a gateway restart turns runs Interrupted, never Failed (O9)."],"statechart":"This is poteto's statechart idea with Bend standing in for TLA+: draw the flow, write the laws, let the prover check the model, then replay real history through it to find where reality broke the rules. Here the laws are proven theorems about the same code that runs in this page, and the reports supply the incident counts.","roles":"The guards are ROLES-v0 in code: only Opus/Sol write code, CI and Opus land work but never their own, Kevin alone accepts and is treated as a batched queue, free models/Jev/SLMs pick and rank but never implement."},"sources":[{"path":"WorkItem.bend","upstream":"kvnloo/z0intelligence@b4c06eefb1fb276e4b999f9e59bbf58bbd9a6f74:bend/work_item_fsm/fsm.bend","gitBlob":"3e0e9922c8d9b13eb6f7647f8fb6128adcf009ea","kind":"bend-model"},{"path":"WorkerSupervision.bend","upstream":"kvnloo/z0intelligence@b4c06eefb1fb276e4b999f9e59bbf58bbd9a6f74:bend/worker_supervision_fsm/fsm.bend","gitBlob":"30db3271ad03a4d59857dbb83842c8358f2be1ef","kind":"bend-model"},{"path":"work-item.mmd","upstream":"kvnloo/z0intelligence@b4c06eefb1fb276e4b999f9e59bbf58bbd9a6f74:docs/fsm/work-item.mmd","gitBlob":"c5d3e07d02d6edb5171c70017811dda628a8a4ff","kind":"documented-statechart"},{"path":"worker-supervision.mmd","upstream":"kvnloo/z0intelligence@b4c06eefb1fb276e4b999f9e59bbf58bbd9a6f74:docs/fsm/worker-supervision.mmd","gitBlob":"11edb752608ed203970019f963b32768017b58ce","kind":"documented-statechart"},{"path":"IntegrationOwner.bend","upstream":"kvnloo/z0intelligence@1ef432f91223e74dcfb756c590aae82a950999ed:bend/integration_owner_fsm/fsm.bend","gitBlob":"beb728aad382ebcad19f8d602ab6a5cdafd9fe75","kind":"bend-model"},{"path":"integration-owner.mmd","upstream":"kvnloo/z0intelligence@1ef432f91223e74dcfb756c590aae82a950999ed:docs/fsm/integration-owner.mmd","gitBlob":"ba3f617a2362e65bbc2fa9a6872601d9e795fd55","kind":"documented-statechart"},{"path":"Ops.bend","upstream":"kvnloo/z0intelligence@24fc31e6f54b466e3daaba6d99d9fee6dc08fe3a:bend/ops_fsm/ops.bend","gitBlob":"9c28f8d2b87a61a6f00aa910ad49e37d7deb3ad6","kind":"bend-model"}],"proofs":[{"project":"bend/work_item_fsm","pr":"kvnloo/z0intelligence#183","commit":"eef21051b1910bcda14542fe5859414f629e4fad","lawsBlob":"b564659c0471b66022c813933c4a99c0b342011e","proofBlob":"db234e6c68f363dbe56571dc749cc9203b3614ea","verdict":"pass","bend":"2.0.34","verifiedAt":"2026-10-21T03:45:45Z","scope":"bend-emitted-book; source_semantics_attested=false"},{"project":"bend/worker_supervision_fsm","pr":"kvnloo/z0intelligence#184","commit":"b4c06eefb1fb276e4b999f9e59bbf58bbd9a6f74","lawsBlob":"5b5709d78a04205df93c4723a5577951053b7ae4","proofBlob":"f12965b9db0b19ed39c4dda25bee7f3a19b7f27e","verdict":"pass","bend":"2.0.34","verifiedAt":"2026-10-21T05:08:25Z","scope":"bend-emitted-book; source_semantics_attested=false"},{"project":"bend/integration_owner_fsm","pr":"kvnloo/z0intelligence#188","commit":"1ef432f91223e74dcfb756c590aae82a950999ed","verdict":"pass","bend":"2.0.34","verifiedAt":"2026-10-21T07:40:49.968160+00:00","scope":"bend-emitted-book; source_semantics_attested=false"},{"project":"bend/ops_fsm","pr":"kvnloo/z0intelligence#192","commit":"24fc31e6f54b466e3daaba6d99d9fee6dc08fe3a","lawsBlob":"593933b921518c58dca32b71fbd8443a15886ecf","proofBlob":"36088d3b740c05ba4b1635e6a680643614ece33b","verdict":"pass","bend":"2.0.34","verifiedAt":"2026-10-21T22:57:31.892044+00:00","scope":"bend-emitted-book; source_semantics_attested=false; receipt 78fe327d9e3e4b19adb599368c37bca5"}],"provenance":{"producer":"docs/spec-diagram/fsm/build.mjs","compilerPin":"bend 2.0.34","compilerIdentitySha256":"66e5faf92d75d6e10a11427c8e4f3df72a4c14b1263a04431fdc015a5aa21317","note":"Same compiler identity that produced the PROOF.bend pass receipts. The .files architecture diagram keeps its own 2.0.37 pin."}};
export const bendSourceSha256 = {"Runtime.bend":"90497942b4ac5460fcfc3708006646e44d69bdb21758d62df04590b36a15d130","WorkItem.bend":"f0465c394b77fed96e577568a7523b139e184dcabf973017bfbe681e74aaf29f","WorkerSupervision.bend":"5acf2bd7deb05bc78ea0ec36836957da625a4e4bde54fb59726fed4338d4f61a","IntegrationOwner.bend":"85cee91b17c81c817f7ed2d0c951fa0ad49d77f3289ceb6deae82349cf303a2a","Ops.bend":"ce1b4595c03bbd17bf99e4798fe6e830ebd648f8a7e19e26743069da5b4ce68d","OpsLayer.bend":"840faa3d1aa0979111dd9eca8df409e850409de79264b3395964c047c56453cc"};
