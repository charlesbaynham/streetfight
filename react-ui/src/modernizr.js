/*! modernizr 3.6.0 (Custom Build) | MIT *
 * https://modernizr.com/download/?-flash-fullscreen-geolocation-vibrate-setclasses !*/
!(function (e, n, t) {
  function r(e, n) {
    return typeof e === n;
  }
  function o() {
    var e, n, t, o, i, s, a;
    for (var l in _)
      if (_.hasOwnProperty(l)) {
        if (
          ((e = []),
          (n = _[l]),
          n.name &&
            (e.push(n.name.toLowerCase()),
            n.options && n.options.aliases && n.options.aliases.length))
        )
          for (t = 0; t < n.options.aliases.length; t++)
            e.push(n.options.aliases[t].toLowerCase());
        for (o = r(n.fn, "function") ? n.fn() : n.fn, i = 0; i < e.length; i++)
          (s = e[i]),
            (a = s.split(".")),
            1 === a.length
              ? (Modernizr[a[0]] = o)
              : (!Modernizr[a[0]] ||
                  Modernizr[a[0]] instanceof Boolean ||
                  (Modernizr[a[0]] = new Boolean(Modernizr[a[0]])),
                (Modernizr[a[0]][a[1]] = o)),
            C.push((o ? "" : "no-") + a.join("-"));
      }
  }
  function i(e) {
    var n = b.className,
      t = Modernizr._config.classPrefix || "";
    if ((S && (n = n.baseVal), Modernizr._config.enableJSClass)) {
      var r = new RegExp("(^|\\s)" + t + "no-js(\\s|$)");
      n = n.replace(r, "$1" + t + "js$2");
    }
    Modernizr._config.enableClasses &&
      ((n += " " + t + e.join(" " + t)),
      S ? (b.className.baseVal = n) : (b.className = n));
  }
  function s(e) {
    return e
      .replace(/([a-z])-([a-z])/g, function (e, n, t) {
        return n + t.toUpperCase();
      })
      .replace(/^-/, "");
  }
  function a() {
    return "function" != typeof n.createElement
      ? n.createElement(arguments[0])
      : S
        ? n.createElementNS.call(n, "http://www.w3.org/2000/svg", arguments[0])
        : n.createElement.apply(n, arguments);
  }
  function l() {
    var e = n.body;
    return e || ((e = a(S ? "svg" : "body")), (e.fake = !0)), e;
  }
  function f(e, n) {
    return !!~("" + e).indexOf(n);
  }
  function u(e, n) {
    return function () {
      return e.apply(n, arguments);
    };
  }
  function c(e, n, t) {
    var o;
    for (var i in e)
      if (e[i] in n)
        return t === !1
          ? e[i]
          : ((o = n[e[i]]), r(o, "function") ? u(o, t || n) : o);
    return !1;
  }
  function d(e, t, r, o) {
    var i,
      s,
      f,
      u,
      c = "modernizr",
      d = a("div"),
      p = l();
    if (parseInt(r, 10))
      for (; r--; )
        (f = a("div")), (f.id = o ? o[r] : c + (r + 1)), d.appendChild(f);
    return (
      (i = a("style")),
      (i.type = "text/css"),
      (i.id = "s" + c),
      (p.fake ? p : d).appendChild(i),
      p.appendChild(d),
      i.styleSheet
        ? (i.styleSheet.cssText = e)
        : i.appendChild(n.createTextNode(e)),
      (d.id = c),
      p.fake &&
        ((p.style.background = ""),
        (p.style.overflow = "hidden"),
        (u = b.style.overflow),
        (b.style.overflow = "hidden"),
        b.appendChild(p)),
      (s = t(d, e)),
      p.fake
        ? (p.parentNode.removeChild(p), (b.style.overflow = u), b.offsetHeight)
        : d.parentNode.removeChild(d),
      !!s
    );
  }
  function p(n, t, r) {
    var o;
    if ("getComputedStyle" in e) {
      o = getComputedStyle.call(e, n, t);
      var i = e.console;
      if (null !== o) r && (o = o.getPropertyValue(r));
      else if (i) {
        var s = i.error ? "error" : "log";
        i[s].call(
          i,
          "getComputedStyle returning null, its possible modernizr test results are inaccurate",
        );
      }
    } else o = !t && n.currentStyle && n.currentStyle[r];
    return o;
  }
  function v(e) {
    return e
      .replace(/([A-Z])/g, function (e, n) {
        return "-" + n.toLowerCase();
      })
      .replace(/^ms-/, "-ms-");
  }
  function h(n, r) {
    var o = n.length;
    if ("CSS" in e && "supports" in e.CSS) {
      for (; o--; ) if (e.CSS.supports(v(n[o]), r)) return !0;
      return !1;
    }
    if ("CSSSupportsRule" in e) {
      for (var i = []; o--; ) i.push("(" + v(n[o]) + ":" + r + ")");
      return (
        (i = i.join(" or ")),
        d(
          "@supports (" + i + ") { #modernizr { position: absolute; } }",
          function (e) {
            return "absolute" == p(e, null, "position");
          },
        )
      );
    }
    return t;
  }
  function m(e, n, o, i) {
    function l() {
      c && (delete j.style, delete j.modElem);
    }
    if (((i = r(i, "undefined") ? !1 : i), !r(o, "undefined"))) {
      var u = h(e, o);
      if (!r(u, "undefined")) return u;
    }
    for (
      var c, d, p, v, m, g = ["modernizr", "tspan", "samp"];
      !j.style && g.length;

    )
      (c = !0), (j.modElem = a(g.shift())), (j.style = j.modElem.style);
    for (p = e.length, d = 0; p > d; d++)
      if (
        ((v = e[d]),
        (m = j.style[v]),
        f(v, "-") && (v = s(v)),
        j.style[v] !== t)
      ) {
        if (i || r(o, "undefined")) return l(), "pfx" == n ? v : !0;
        try {
          j.style[v] = o;
        } catch (y) {}
        if (j.style[v] != m) return l(), "pfx" == n ? v : !0;
      }
    return l(), !1;
  }
  function g(e, n, t, o, i) {
    var s = e.charAt(0).toUpperCase() + e.slice(1),
      a = (e + " " + k.join(s + " ") + s).split(" ");
    return r(n, "string") || r(n, "undefined")
      ? m(a, n, o, i)
      : ((a = (e + " " + P.join(s + " ") + s).split(" ")), c(a, n, t));
  }
  function y(e, n) {
    if ("object" == typeof e) for (var t in e) z(e, t) && y(t, e[t]);
    else {
      e = e.toLowerCase();
      var r = e.split("."),
        o = Modernizr[r[0]];
      if ((2 == r.length && (o = o[r[1]]), "undefined" != typeof o))
        return Modernizr;
      (n = "function" == typeof n ? n() : n),
        1 == r.length
          ? (Modernizr[r[0]] = n)
          : (!Modernizr[r[0]] ||
              Modernizr[r[0]] instanceof Boolean ||
              (Modernizr[r[0]] = new Boolean(Modernizr[r[0]])),
            (Modernizr[r[0]][r[1]] = n)),
        i([(n && 0 != n ? "" : "no-") + r.join("-")]),
        Modernizr._trigger(e, n);
    }
    return Modernizr;
  }
  var C = [],
    _ = [],
    w = {
      _version: "3.6.0",
      _config: {
        classPrefix: "",
        enableClasses: !0,
        enableJSClass: !0,
        usePrefixes: !0,
      },
      _q: [],
      on: function (e, n) {
        var t = this;
        setTimeout(function () {
          n(t[e]);
        }, 0);
      },
      addTest: function (e, n, t) {
        _.push({ name: e, fn: n, options: t });
      },
      addAsyncTest: function (e) {
        _.push({ name: null, fn: e });
      },
    },
    Modernizr = function () {};
  (Modernizr.prototype = w),
    (Modernizr = new Modernizr()),
    Modernizr.addTest("geolocation", "geolocation" in navigator);
  var b = n.documentElement,
    S = "svg" === b.nodeName.toLowerCase(),
    x = "Moz O ms Webkit",
    k = w._config.usePrefixes ? x.split(" ") : [];
  w._cssomPrefixes = k;
  var T = function (n) {
    var r,
      o = prefixes.length,
      i = e.CSSRule;
    if ("undefined" == typeof i) return t;
    if (!n) return !1;
    if (
      ((n = n.replace(/^@/, "")),
      (r = n.replace(/-/g, "_").toUpperCase() + "_RULE"),
      r in i)
    )
      return "@" + n;
    for (var s = 0; o > s; s++) {
      var a = prefixes[s],
        l = a.toUpperCase() + "_" + r;
      if (l in i) return "@-" + a.toLowerCase() + "-" + n;
    }
    return !1;
  };
  w.atRule = T;
  var P = w._config.usePrefixes ? x.toLowerCase().split(" ") : [];
  w._domPrefixes = P;
  var N = { elem: a("modernizr") };
  Modernizr._q.push(function () {
    delete N.elem;
  });
  var j = { style: N.elem.style };
  Modernizr._q.unshift(function () {
    delete j.style;
  }),
    (w.testAllProps = g);
  var E = (w.prefixed = function (e, n, t) {
    return 0 === e.indexOf("@")
      ? T(e)
      : (-1 != e.indexOf("-") && (e = s(e)), n ? g(e, n, t) : g(e, "pfx"));
  });
  Modernizr.addTest(
    "fullscreen",
    !(!E("exitFullscreen", n, !1) && !E("cancelFullScreen", n, !1)),
  ),
    Modernizr.addTest("vibrate", !!E("vibrate", navigator));
  var z;
  !(function () {
    var e = {}.hasOwnProperty;
    z =
      r(e, "undefined") || r(e.call, "undefined")
        ? function (e, n) {
            return n in e && r(e.constructor.prototype[n], "undefined");
          }
        : function (n, t) {
            return e.call(n, t);
          };
  })(),
    (w._l = {}),
    (w.on = function (e, n) {
      this._l[e] || (this._l[e] = []),
        this._l[e].push(n),
        Modernizr.hasOwnProperty(e) &&
          setTimeout(function () {
            Modernizr._trigger(e, Modernizr[e]);
          }, 0);
    }),
    (w._trigger = function (e, n) {
      if (this._l[e]) {
        var t = this._l[e];
        setTimeout(function () {
          var e, r;
          for (e = 0; e < t.length; e++) (r = t[e])(n);
        }, 0),
          delete this._l[e];
      }
    }),
    Modernizr._q.push(function () {
      w.addTest = y;
    }),
    Modernizr.addAsyncTest(function () {
      var t,
        r,
        o = function (e) {
          b.contains(e) || b.appendChild(e);
        },
        i = function (e) {
          e.fake && e.parentNode && e.parentNode.removeChild(e);
        },
        s = function (e, n) {
          var t = !!e;
          if (
            (t && ((t = new Boolean(t)), (t.blocked = "blocked" === e)),
            y("flash", function () {
              return t;
            }),
            n && p.contains(n))
          ) {
            for (; n.parentNode !== p; ) n = n.parentNode;
            p.removeChild(n);
          }
        };
      try {
        r =
          "ActiveXObject" in e &&
          "Pan" in new e.ActiveXObject("ShockwaveFlash.ShockwaveFlash");
      } catch (f) {}
      if (
        ((t = !(
          ("plugins" in navigator && "Shockwave Flash" in navigator.plugins) ||
          r
        )),
        t || S)
      )
        s(!1);
      else {
        var u,
          c,
          d = a("embed"),
          p = l();
        if (
          ((d.type = "application/x-shockwave-flash"),
          p.appendChild(d),
          !("Pan" in d || r))
        )
          return o(p), s("blocked", d), void i(p);
        (u = function () {
          return (
            o(p),
            b.contains(p)
              ? (b.contains(d)
                  ? ((c = d.style.cssText),
                    "" !== c ? s("blocked", d) : s(!0, d))
                  : s("blocked"),
                void i(p))
              : ((p = n.body || p),
                (d = a("embed")),
                (d.type = "application/x-shockwave-flash"),
                p.appendChild(d),
                setTimeout(u, 1e3))
          );
        }),
          setTimeout(u, 10);
      }
    }),
    o(),
    i(C),
    delete w.addTest,
    delete w.addAsyncTest;
  for (var O = 0; O < Modernizr._q.length; O++) Modernizr._q[O]();
  e.Modernizr = Modernizr;
})(window, document);
