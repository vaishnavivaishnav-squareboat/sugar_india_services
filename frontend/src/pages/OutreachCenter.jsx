import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Zap, Copy, Check, Mail, Send, RefreshCw, MapPin, Search, ArrowUpRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const segColor = (s) => ({
  Hotel: "#143628", Restaurant: "#3D6B56", Cafe: "#8FA39A",
  Bakery: "#B85C38", CloudKitchen: "#D4956A", Catering: "#6B5E44",
  Mithai: "#A0522D", IceCream: "#C4878A"
}[s] || "#5C736A");

const priorityColor = (p) => p === "High" ? "#B85C38" : p === "Medium" ? "#143628" : "#5C736A";

export default function OutreachCenter() {
  const [emails, setEmails] = useState([]);
  const [leads, setLeads] = useState([]);
  const [selectedLead, setSelectedLead] = useState(null);
  const [activeEmail, setActiveEmail] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [leadSearch, setLeadSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const init = async () => {
      const [emailRes, leadRes] = await Promise.all([
        axios.get(`${API}/outreach/emails`),
        axios.get(`${API}/leads`, { params: { limit: 100 } })
      ]);
      setEmails(emailRes.data);
      setLeads(leadRes.data.leads || []);
      setLoading(false);
    };
    init();
  }, []);

  const handleGenerateEmail = async () => {
    if (!selectedLead) return;
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/leads/${selectedLead.id}/generate-email`);
      setEmails(prev => [res.data, ...prev]);
      setActiveEmail(res.data);
    } catch (err) {
      alert("Email generation failed. Please check your API key balance.");
    }
    setGenerating(false);
  };

  const markSent = async (emailId) => {
    const res = await axios.put(`${API}/outreach/${emailId}/mark-sent`);
    setEmails(prev => prev.map(e => e.id === emailId ? res.data : e));
    if (activeEmail?.id === emailId) setActiveEmail(res.data);
  };

  const copyEmail = () => {
    if (!activeEmail) return;
    navigator.clipboard.writeText(`Subject: ${activeEmail.subject}\n\n${activeEmail.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredLeads = leads.filter(l =>
    !leadSearch || l.business_name.toLowerCase().includes(leadSearch.toLowerCase()) ||
    l.city.toLowerCase().includes(leadSearch.toLowerCase())
  );

  const recentByLead = emails.reduce((acc, e) => {
    if (!acc[e.lead_id]) acc[e.lead_id] = e;
    return acc;
  }, {});
  const uniqueLeadEmails = Object.values(recentByLead).slice(0, 20);

  if (loading) {
    return <div className="p-6 animate-pulse"><div className="h-8 bg-[#EAECE6] rounded w-48 mb-6" /></div>;
  }

  return (
    <div className="p-6" style={{ backgroundColor: "#F8F9F6", minHeight: "100vh" }}>
      {/* Header */}
      <div className="mb-5 animate-fade-in">
        <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-1" style={{ letterSpacing: '0.2em' }}>AI Outreach</p>
        <h1 className="text-2xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
          Outreach Center
        </h1>
        <p className="text-sm text-[#5C736A] mt-1">Generate and manage AI-personalized sales emails</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* LEFT: Lead Selector */}
        <div className="space-y-4 animate-fade-in animate-fade-in-delay-1">
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-4">
            <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-3" style={{ letterSpacing: '0.15em' }}>Select Lead</p>
            <div className="relative mb-3">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9CA3AF]" />
              <input
                data-testid="lead-search-outreach"
                value={leadSearch}
                onChange={e => setLeadSearch(e.target.value)}
                placeholder="Search leads..."
                className="w-full pl-8 border border-[#DCE1D9] rounded-md py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#143628]"
              />
            </div>
            <div className="space-y-1 max-h-[320px] overflow-y-auto">
              {filteredLeads.slice(0, 30).map((lead, i) => (
                <button
                  key={lead.id}
                  data-testid={`lead-selector-${i}`}
                  onClick={() => setSelectedLead(lead)}
                  className={`w-full text-left p-2.5 rounded-lg border transition-all ${selectedLead?.id === lead.id ? "border-[#143628] bg-[#143628]/5" : "border-transparent hover:bg-[#F8F9F6]"}`}
                >
                  <p className="text-xs font-medium text-[#16221E] truncate">{lead.business_name}</p>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-xs text-[#9CA3AF] flex items-center gap-1">
                      <MapPin size={9} /> {lead.city}
                    </span>
                    <div className="flex items-center gap-1">
                      <span className="text-[9px] text-white px-1.5 py-0.5 rounded" style={{ backgroundColor: segColor(lead.segment) }}>{lead.segment}</span>
                      <span className="text-[9px] font-bold" style={{ color: priorityColor(lead.priority) }}>{lead.ai_score}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Selected Lead Info */}
          {selectedLead && (
            <div className="bg-[#143628] text-white rounded-xl p-4 animate-fade-in" data-testid="selected-lead-info">
              <p className="text-xs text-white/50 uppercase tracking-widest mb-2" style={{ letterSpacing: '0.15em' }}>Selected</p>
              <p className="font-semibold text-sm">{selectedLead.business_name}</p>
              <p className="text-xs text-white/60 mt-0.5">{selectedLead.segment} · {selectedLead.city}</p>
              {selectedLead.decision_maker_name && (
                <p className="text-xs text-white/60 mt-1">{selectedLead.decision_maker_name} · {selectedLead.decision_maker_role}</p>
              )}
              <div className="flex gap-2 mt-3">
                <button
                  data-testid="generate-email-outreach-btn"
                  onClick={handleGenerateEmail}
                  disabled={generating}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[#143628] text-xs font-semibold bg-white hover:bg-[#F0F0F0] disabled:opacity-60 transition-opacity"
                >
                  {generating ? <><RefreshCw size={12} className="animate-spin" /> Generating...</> : <><Zap size={12} /> Generate Email</>}
                </button>
                <button
                  data-testid="view-lead-detail-btn"
                  onClick={() => navigate(`/leads/${selectedLead.id}`)}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                  title="View lead detail"
                >
                  <ArrowUpRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* CENTER: Email Preview */}
        <div className="space-y-4 animate-fade-in animate-fade-in-delay-2">
          {activeEmail ? (
            <div className="bg-white border border-[#DCE1D9] rounded-xl overflow-hidden" data-testid="active-email-panel">
              {/* Email header */}
              <div className="bg-[#F8F9F6] border-b border-[#DCE1D9] px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[#9CA3AF] uppercase tracking-widest mb-1" style={{ letterSpacing: '0.1em' }}>Subject</p>
                    <p className="text-sm font-semibold text-[#16221E]">{activeEmail.subject}</p>
                  </div>
                  <div className="flex gap-1.5 flex-shrink-0">
                    <button
                      data-testid="copy-email-outreach-btn"
                      onClick={copyEmail}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-[#DCE1D9] text-xs text-[#5C736A] hover:bg-[#EDF0EA]"
                    >
                      {copied ? <><Check size={12} className="text-green-600" /> Copied</> : <><Copy size={12} /> Copy</>}
                    </button>
                    {activeEmail.status === 'draft' && (
                      <button
                        data-testid="mark-sent-outreach-btn"
                        onClick={() => markSent(activeEmail.id)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-white bg-[#143628] hover:opacity-90"
                      >
                        <Send size={12} /> Mark Sent
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 mt-3 text-xs text-[#9CA3AF]">
                  <span className="flex items-center gap-1"><Mail size={11} /> To: {activeEmail.lead_name}</span>
                  <span>·</span>
                  <span>{new Date(activeEmail.generated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs ${activeEmail.status === 'sent' ? 'bg-green-100 text-green-700' : 'bg-[#EDF0EA] text-[#5C736A]'}`}>
                    {activeEmail.status}
                  </span>
                </div>
              </div>
              {/* Email body */}
              <div className="p-5">
                <div className="email-editor">{activeEmail.body}</div>
              </div>
            </div>
          ) : (
            <div className="bg-white border border-[#DCE1D9] rounded-xl p-16 flex flex-col items-center justify-center text-center" data-testid="email-empty-state">
              <Mail size={36} className="text-[#DCE1D9] mb-3" strokeWidth={1} />
              <p className="text-sm font-medium text-[#16221E]">No email selected</p>
              <p className="text-xs text-[#9CA3AF] mt-1">Select a lead and generate an AI email,<br />or click an email from the history</p>
            </div>
          )}
        </div>

        {/* RIGHT: Email History */}
        <div className="animate-fade-in animate-fade-in-delay-3">
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs uppercase tracking-widest text-[#5C736A]" style={{ letterSpacing: '0.15em' }}>Email History</p>
              <span className="text-xs bg-[#EDF0EA] text-[#5C736A] px-2 py-0.5 rounded-full">{emails.length}</span>
            </div>
            {emails.length === 0 ? (
              <p className="text-xs text-[#9CA3AF] text-center py-8">No emails generated yet</p>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {emails.map((email, i) => (
                  <button
                    key={email.id}
                    data-testid={`email-history-item-${i}`}
                    onClick={() => setActiveEmail(email)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${activeEmail?.id === email.id ? "border-[#143628] bg-[#143628]/5" : "border-[#F0F3EF] hover:bg-[#F8F9F6]"}`}
                  >
                    <p className="text-xs font-medium text-[#16221E] truncate">{email.lead_name}</p>
                    <p className="text-xs text-[#5C736A] truncate mt-0.5">{email.subject || "—"}</p>
                    <div className="flex items-center justify-between mt-1.5">
                      <div className="flex items-center gap-1 text-[#9CA3AF]">
                        <MapPin size={9} />
                        <span className="text-[10px]">{email.lead_city}</span>
                        {email.lead_segment && (
                          <span className="text-[9px] text-white px-1 py-0.5 rounded ml-1" style={{ backgroundColor: segColor(email.lead_segment) }}>
                            {email.lead_segment}
                          </span>
                        )}
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${email.status === 'sent' ? 'bg-green-100 text-green-700' : 'bg-[#EDF0EA] text-[#5C736A]'}`}>
                        {email.status}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
