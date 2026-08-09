import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = {
  listCases: (lang) => axios.get(`${API}/cases`, { params: { lang } }).then((r) => r.data),
  caseDetail: (id, lang) => axios.get(`${API}/cases/${id}`, { params: { lang } }).then((r) => r.data),
  createSession: (case_id, lang) => axios.post(`${API}/sessions`, { case_id, lang }).then((r) => r.data),
  getSession: (sid) => axios.get(`${API}/sessions/${sid}`).then((r) => r.data),
  sendMessage: (sid, text) => axios.post(`${API}/sessions/${sid}/message`, { text }).then((r) => r.data),
  runExam: (sid, action_id) => axios.post(`${API}/sessions/${sid}/exam`, { action_id }).then((r) => r.data),
  orderTest: (sid, action_id) => axios.post(`${API}/sessions/${sid}/test`, { action_id }).then((r) => r.data),
  xrayAnswer: (sid, test_id, option_id) => axios.post(`${API}/sessions/${sid}/xray-answer`, { test_id, option_id }).then((r) => r.data),
  commit: (sid, body) => axios.post(`${API}/sessions/${sid}/commit`, body).then((r) => r.data),
  score: (sid) => axios.post(`${API}/sessions/${sid}/score`).then((r) => r.data),
  demo: (lang) => axios.get(`${API}/demo`, { params: { lang } }).then((r) => r.data),
};
