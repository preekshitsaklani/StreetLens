"""Bloomberg Desktop API adapter (blpapi). Runs only where a Bloomberg Terminal is logged in (localhost:8194).

Install on the Terminal PC: pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/
Data pulled via the Desktop API is for the licensed user only: never commit it to a public repository.
"""
import datetime as dt
import json
import os

from .paths import COMPANIES

CFG = json.loads((COMPANIES / "_data_fields.json").read_text())["bloomberg"]
HOST, PORT = os.getenv("BLOOMBERG_HOST", "localhost"), int(os.getenv("BLOOMBERG_PORT", "8194"))


def _session():
    import blpapi
    opts = blpapi.SessionOptions()
    opts.setServerHost(HOST)
    opts.setServerPort(PORT)
    s = blpapi.Session(opts)
    if not s.start() or not s.openService("//blp/refdata"):
        raise ConnectionError("No Bloomberg Terminal session on this machine")
    return s, blpapi


def available() -> bool:
    try:
        s, _ = _session()
        s.stop()
        return True
    except Exception:
        return False


def _collect(s, blpapi, timeout_ms=15000):
    while True:
        ev = s.nextEvent(timeout_ms)
        for msg in ev:
            yield msg
        if ev.eventType() in (blpapi.Event.RESPONSE, blpapi.Event.TIMEOUT):
            return


def bdp(securities: list[str], fields: list[str], overrides: dict | None = None) -> dict:
    """Reference data, like =BDP() in Excel. Returns {security: {field: value}}."""
    s, blpapi = _session()
    req = s.getService("//blp/refdata").createRequest("ReferenceDataRequest")
    for sec in securities:
        req.getElement("securities").appendValue(sec)
    for f in fields:
        req.getElement("fields").appendValue(f)
    for k, v in (overrides or {}).items():
        o = req.getElement("overrides").appendElement()
        o.setElement("fieldId", k)
        o.setElement("value", v)
    s.sendRequest(req)
    out = {}
    for msg in _collect(s, blpapi):
        if not msg.hasElement("securityData"):
            continue
        arr = msg.getElement("securityData")
        for i in range(arr.numValues()):
            x = arr.getValueAsElement(i)
            fd = x.getElement("fieldData")
            out[x.getElementAsString("security")] = {f: fd.getElement(f).getValue() for f in fields if fd.hasElement(f)}
    s.stop()
    return out


def bdh(securities: list[str], field: str = "PX_LAST", years: int = 2, periodicity: str = "WEEKLY") -> dict:
    """Historical data, like =BDH() in Excel. Returns {security: [(date, value), ...]}."""
    s, blpapi = _session()
    req = s.getService("//blp/refdata").createRequest("HistoricalDataRequest")
    for sec in securities:
        req.getElement("securities").appendValue(sec)
    req.getElement("fields").appendValue(field)
    end = dt.date.today()
    req.set("startDate", (end - dt.timedelta(days=365 * years)).strftime("%Y%m%d"))
    req.set("endDate", end.strftime("%Y%m%d"))
    req.set("periodicitySelection", periodicity)
    s.sendRequest(req)
    out = {}
    for msg in _collect(s, blpapi):
        if not msg.hasElement("securityData"):
            continue
        sd = msg.getElement("securityData")
        rows = sd.getElement("fieldData")
        out[sd.getElementAsString("security")] = [(str(rows.getValueAsElement(j).getElementAsDatetime("date")),
                                                   rows.getValueAsElement(j).getElementAsFloat(field)) for j in range(rows.numValues())]
    s.stop()
    return out


def fetch(tickers: list[str]) -> dict:
    """Same schema as the Yahoo source. Units normalised: market cap USD bn, ROE and yield as decimals."""
    from .market import beta_from_prices
    secs = {t: CFG["security"].format(ticker=t) for t in tickers}
    f = CFG["fields"]
    ref = bdp(list(secs.values()) + [CFG["rf"], CFG["fed_funds"]], list(f.values()) + ["PX_LAST"])
    hist = bdh(list(secs.values()) + [CFG["index"]])
    out = {"companies": {}, "rates": {"DGS10": ref.get(CFG["rf"], {}).get("PX_LAST"), "DFF": ref.get(CFG["fed_funds"], {}).get("PX_LAST")}}
    for t, sec in secs.items():
        r = ref.get(sec, {})
        g = lambda k, scale=1.0: (r.get(f[k]) / scale) if r.get(f[k]) is not None else None
        out["companies"][t] = {"price": g("price"), "mcap_bn": g("mcap_mn", 1000), "pb": g("pb"), "roe": g("roe_pct", 100),
                               "fwd_pe": g("fwd_pe"), "high52": g("high52"), "low52": g("low52"), "div_yield": g("div_yield_pct", 100),
                               "consensus_tp": g("consensus_tp"), "consensus_eps": g("consensus_eps"), "tbvps": g("tbvps"),
                               "beta": beta_from_prices(hist.get(sec, []), hist.get(CFG["index"], []))}
    return out
