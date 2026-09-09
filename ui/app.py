"""Streamlit ingestion client. All financial access goes through the authenticated API."""
from concurrent.futures import ThreadPoolExecutor
import os
import requests
import streamlit as st

API=os.environ.get("API_BASE_URL","http://api:8000").rstrip("/")
st.set_page_config(page_title="Clinic Finance · Demo",layout="wide")
st.title("Clinic Financial Intelligence")


def call(method,path,token=None,**kwargs):
    headers=kwargs.pop("headers",{})
    if token: headers["Authorization"]="Bearer "+token
    try:
        r=requests.request(method,API+path,headers=headers,timeout=(5,120),**kwargs)
        value=r.json() if r.content else {}
        return r.status_code,value
    except (requests.RequestException,ValueError):
        return 503,{"error":{"message":"The service could not be reached. If an upload was submitted, resend the same file safely to check its result."}}


def message(result):
    if result.get("error",{}).get("code")=="http_401" and "token" in st.session_state:
        executor=st.session_state.get("executor")
        if executor: executor.shutdown(wait=False,cancel_futures=True)
        st.session_state.clear()
        st.session_state.auth_expired=True
        st.rerun()
    st.error(result.get("error",{}).get("message","Request could not be completed."))

if "token" not in st.session_state:
    if st.session_state.pop("auth_expired",False):
        st.warning("Your session expired. Sign in again.")
    with st.form("sign_in"):
        username=st.text_input("Username")
        password=st.text_input("Password",type="password")
        submit=st.form_submit_button("Sign in")
    if submit:
        status,result=call("POST","/api/v1/auth/login",json={"username":username,"password":password})
        if status==200:
            st.session_state.token=result["access_token"]
            st.rerun()
        else: message(result)
    st.stop()

token=st.session_state.token
if st.sidebar.button("Sign out"):
    status,result=call("POST","/api/v1/auth/logout",token)
    if status not in (204,401):
        message(result)
        st.stop()
    future=st.session_state.get("submission")
    if future: future.cancel()
    executor=st.session_state.get("executor")
    if executor: executor.shutdown(wait=False,cancel_futures=True)
    st.session_state.clear()
    st.rerun()

section=st.sidebar.radio("Workspace",["Analytics","Staffing & clinic budget","Financial questions","Imports"])
if section=="Analytics":
    from dashboard import render_dashboard
    render_dashboard(call,message,token)
    st.stop()

if section=="Staffing & clinic budget":
    from simulation import render_simulation
    render_simulation(call,message,token)
    st.stop()

if section=="Financial questions":
    from questions import render_questions
    render_questions(call,message,token)
    st.stop()

st.header("Import financial data")
st.caption("Upload an approved aggregate export and review every rejected row.")
status,options=call("GET","/api/v1/ingestion/config",token)
if status==401:
    st.session_state.pop("token",None)
    st.session_state.auth_expired=True
    st.rerun()
if status!=200:
    message(options); st.stop()
if not options["enabled"]:
    st.info("Imports are not configured for this account. Your administrator must approve the export mapping and access first.")
    st.stop()
if options["mode"]=="synthetic":
    st.warning("Synthetic demo only. Do not upload real clinic or patient data.")

profile=st.selectbox("Export mapping",options["profiles"])
st.caption("CSV, single-sheet XLSX, or computer-generated PDF with extractable tables · maximum 10 MiB. No scanned PDFs.")
file=st.file_uploader("Choose aggregate financial export",type=options["formats"])
if st.session_state.get("last_error"):
    message(st.session_state.last_error)
confirmed=st.checkbox("This file contains only approved aggregate financial data, with no patient identifiers.")
if st.button("Submit import",disabled=file is None or not confirmed or "submission" in st.session_state):
    data=file.getvalue()
    if len(data)>options["max_bytes"]:
        st.error("File exceeds 10 MiB.")
    else:
        if "executor" not in st.session_state:
            st.session_state.executor=ThreadPoolExecutor(max_workers=1)
        st.session_state.pop("last_error",None)
        st.session_state.pop("final_summary",None)
        st.session_state.submission=st.session_state.executor.submit(
            call,"POST","/api/v1/uploads/"+file.name.rsplit(".",1)[-1].lower(),token,
            params={"profile":profile},data=data,headers={"Content-Type":"application/octet-stream"})
        st.rerun()

@st.fragment(run_every="2s")
def progress():
    future=st.session_state.get("submission")
    if future:
        if not future.done():
            st.info("Checking file structure and preparing the import… You can continue using this page.")
            return
        status,result=future.result()
        del st.session_state.submission
        if status not in (200,202):
            message(result)
            st.session_state.last_error=result
        else:
            st.session_state.upload_id=result["upload_id"]
            st.session_state.duplicate=result.get("duplicate",False)
            st.session_state.pop("last_error",None)
        st.rerun()
    upload_id=st.session_state.get("upload_id")
    if not upload_id: return
    result=st.session_state.get("final_summary")
    if result is None:
        status,result=call("GET","/api/v1/uploads/"+upload_id,token)
        if status!=200: message(result); return
        if result["status"]=="completed": st.session_state.final_summary=result
    st.subheader("Import summary")
    st.caption("Reference: "+upload_id)
    if st.session_state.get("duplicate"):
        st.info("This exact file was already submitted. Showing its existing import; no duplicate transactions were created.")
    state=result["status"]
    if state=="pending":
        st.info("Queued or processing. Counts become final when the worker finishes.")
        return
    if state=="failed":
        st.error("Processing failed. No partial financial rows were committed. You can retry this same import.")
        if st.button("Retry failed import"):
            status,retry=call("POST",f"/api/v1/uploads/{upload_id}/retry",token)
            if status!=202: message(retry)
            else: st.rerun()
        return
    left,middle,right=st.columns(3)
    left.metric("Rows examined",result["total_rows"])
    middle.metric("Accepted",result["rows_accepted"])
    right.metric("Rejected",result["rows_rejected"])
    if result["rows_rejected"]:
        st.warning("Review rejected rows in the source export. Correcting and re-uploading a file with already accepted rows may duplicate those rows; byte-level deduplication does not detect overlapping exports.")
        st.dataframe(result["rejections"],hide_index=True,width="stretch")
    else: st.success("All rows were imported.")

progress()
