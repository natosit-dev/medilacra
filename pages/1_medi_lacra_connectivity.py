
import os
import json
import socket
import ssl
import time
from datetime import datetime

import streamlit as st
import requests

from hl7_demo.sdoh import (
    get_air_quality_by_zip, build_obx_air_quality,
    get_poverty_pct_by_zcta, build_obx_poverty_pct,
    get_police_station_count_by_zip, build_obx_police_count,
)
from hl7_demo.config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR


st.set_page_config(page_title="MediLacra — Connectivity Tester", layout="wide")
st.title("🌐 MediLacra — Connectivity Tester")
st.caption("Diagnose network access for APIs, engines, and endpoints.")

with st.sidebar:
    st.header("Quick Settings")
    default_key = os.getenv("AIRNOW_API_KEY", "") or AIRNOW_API_KEY
    airnow_key = st.text_input("AirNow API Key", default_key, type="password")
    miles = st.number_input("AirNow radius (miles)", min_value=1, max_value=200, value=int(AIRNOW_MILES_DEFAULT), step=1)
    st.caption(f"ACS Year: {ACS_YEAR}")

tab_net, tab_http, tab_mllp, tab_api = st.tabs(["DNS / TCP / TLS", "HTTP Request", "MLLP Sender", "SDOH API Probes"])

# -------------------------------
# DNS / TCP / TLS diagnostics
# -------------------------------
with tab_net:
    st.subheader("DNS / TCP / TLS")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        host = st.text_input("Hostname or IP", "iddqd.sonder.pizza")
    with c2:
        port = st.number_input("Port", min_value=1, max_value=65535, value=443, step=1)
    with c3:
        use_tls = st.toggle("TLS handshake", value=True)

    timeout = st.number_input("Timeout (seconds)", min_value=1, max_value=30, value=6, key="net_timeout")

    if st.button("Run Network Check", type="primary"):
        results = {}
        t0 = time.time()
        # DNS resolution
        try:
            infos = socket.getaddrinfo(host, None)
            addrs = sorted({i[4][0] for i in infos})
            results["dns_addresses"] = addrs
            st.success(f"DNS OK: {', '.join(addrs)}")
        except Exception as e:
            st.error(f"DNS resolution failed: {e}")
        # TCP connect (and optional TLS)
        try:
            t1 = time.time()
            with socket.create_connection((host, int(port)), timeout=timeout) as sock:
                tcp_latency = (time.time() - t1) * 1000
                results["tcp_latency_ms"] = round(tcp_latency, 1)
                st.write(f"TCP connected in **{tcp_latency:.1f} ms**")
                if use_tls:
                    context = ssl.create_default_context()
                    t2 = time.time()
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        tls_latency = (time.time() - t2) * 1000
                        cert = ssock.getpeercert()
                        results["tls_latency_ms"] = round(tls_latency, 1)
                        st.write(f"TLS handshake in **{tls_latency:.1f} ms**")
                        # Cert summary
                        subject = dict(x[0] for x in cert.get("subject", []))
                        issuer = dict(x[0] for x in cert.get("issuer", []))
                        not_after = cert.get("notAfter")
                        exp_dt = None
                        if not_after:
                            try:
                                exp_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                            except Exception:
                                exp_dt = None
                        days_left = None
                        if exp_dt:
                            days_left = (exp_dt - datetime.utcnow()).days
                        st.info(f"Cert subject: {subject.get('commonName','?')} • Issuer: {issuer.get('commonName','?')} • Expires: {not_after} • Days left: {days_left}")
                else:
                    st.info("TLS disabled — TCP-only check complete.")
        except Exception as e:
            st.error(f"TCP/TLS failure: {e}")
        st.caption(f"Total elapsed: {(time.time()-t0):.2f}s")

    st.divider()
    st.subheader("Quick Port Probes")
    host_qp = st.text_input("Host for quick probes", "iddqd.sonder.pizza", key="qp_host")
    ports = st.text_input("Ports (comma separated)", "22,80,443,8090,8091,8092,2575,2576")
    if st.button("Probe Ports"):
        open_ports = []
        for p in [int(x.strip()) for x in ports.split(",") if x.strip().isdigit()]:
            try:
                with socket.create_connection((host_qp, p), timeout=2) as _:
                    open_ports.append(p)
            except Exception:
                pass
        if open_ports:
            st.success(f"Open ports: {', '.join(map(str, open_ports))}")
        else:
            st.warning("No probed ports responded in time.")

# -------------------------------
# HTTP request playground
# -------------------------------
with tab_http:
    st.subheader("HTTP Request")
    url = st.text_input("URL", "https://httpbin.org/get")
    method = st.selectbox("Method", ["GET","POST","PUT","PATCH","DELETE"])
    headers_text = st.text_area("Headers (JSON)", '{"User-Agent":"MediLacra/1.0"}')
    body = st.text_area("Body")
    verify_tls = st.toggle("Verify TLS certificate", True)
    timeout_http = st.number_input("Timeout (seconds)", 1, 60, 10, key="http_timeout")
    if st.button("Send HTTP Request", type="primary"):
        try:
            headers = json.loads(headers_text) if headers_text.strip() else {}
        except Exception as e:
            st.error(f"Invalid headers JSON: {e}")
            headers = {}
        t0 = time.time()
        try:
            resp = requests.request(method, url, headers=headers, data=body if method in ("POST","PUT","PATCH") else None, timeout=timeout_http, verify=verify_tls)
            elapsed = (time.time()-t0)*1000
            st.success(f"{resp.status_code} {resp.reason} • {elapsed:.1f} ms")
            st.text("Response headers")
            st.code("\n".join([f"{k}: {v}" for k, v in resp.headers.items()]))
            content_type = resp.headers.get("content-type","")
            st.text("Response preview")
            if "application/json" in content_type:
                st.json(resp.json())
            else:
                st.code(resp.text[:2000])
        except Exception as e:
            st.error(f"HTTP error: {e}")

# -------------------------------
# MLLP sender
# -------------------------------
with tab_mllp:
    st.subheader("MLLP (HL7 over TCP)")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        m_host = st.text_input("MLLP Host", "localhost")
    with c2:
        m_port = st.number_input("MLLP Port", min_value=1, max_value=65535, value=2575)
    with c3:
        m_timeout = st.number_input("Timeout (seconds)", 1, 30, 6, key="mllp_timeout")
    default_hl7 = "MSH|^~\\&|MediLacra|Demo|Dest|Demo|{ts}||ADT^A01^ADT_A01|CTRL|P|2.5\rEVN|A01|{ts}\rPID|1||RAD00001||DOE^JANE||19700101|F|||123 MAIN ST^^CAMBRIDGE^MA^02139"
    msg = st.text_area("HL7 Message (no MLLP wrappers)", default_hl7.format(ts=datetime.utcnow().strftime("%Y%m%d%H%M%S")), height=180)
    if st.button("Send via MLLP", type="primary"):
        try:
            with socket.create_connection((m_host, int(m_port)), timeout=int(m_timeout)) as s:
                # Wrap with MLLP: <VT> message <FS><CR>
                payload = b"\x0b" + msg.encode("utf-8") + b"\x1c\x0d"
                t0 = time.time()
                s.sendall(payload)
                s.settimeout(int(m_timeout))
                # Try to read an ACK (optional)
                data = s.recv(4096)
                elapsed = (time.time()-t0)*1000
                if data:
                    # Strip MLLP wrappers if present
                    if data.startswith(b"\x0b") and data.endswith(b"\x1c\x0d"):
                        data = data[1:-2]
                    st.success(f"Sent in {elapsed:.1f} ms — Received {len(data)} bytes")
                    st.code(data.decode("utf-8", errors="replace"))
                else:
                    st.success(f"Sent in {elapsed:.1f} ms — No response")
        except Exception as e:
            st.error(f"MLLP error: {e}")

# -------------------------------
# SDOH API timed probes
# -------------------------------
with tab_api:
    st.subheader("SDOH API Probes (timed)")
    c1, c2, c3 = st.columns(3)
    with c1:
        z_aqi = st.text_input("ZIP for AirNow", "02139")
    with c2:
        z_acs = st.text_input("ZCTA for ACS", "02139")


    if st.button("Run Probes", type="primary"):
        rows = []
        # AirNow
        os.environ["AIRNOW_API_KEY"] = airnow_key or ""
        t0 = time.time()
        aqi = get_air_quality_by_zip(z_aqi, miles=int(miles))
        t_aqi = (time.time()-t0)*1000.0
        rows.append(("AirNow", "aq/observation/zipCode/current", z_aqi, "OK" if aqi else "NO DATA", f"{t_aqi:.1f} ms"))
        # ACS
        t0 = time.time()
        pct = get_poverty_pct_by_zcta(z_acs)
        t_acs = (time.time()-t0)*1000.0
        rows.append(("Census ACS", "acs5/B17001", z_acs, "OK" if pct is not None else "NO DATA", f"{t_acs:.1f} ms"))
         # Render table
        st.table({"Service":[r[0] for r in rows], "Endpoint":[r[1] for r in rows], "Input":[r[2] for r in rows], "Result":[r[3] for r in rows], "Latency":[r[4] for r in rows]})
        # OBX previews
        with st.expander("OBX Previews"):
            if aqi: st.code(build_obx_air_quality(aqi))
            if pct is not None: st.code(build_obx_poverty_pct(pct))
           
