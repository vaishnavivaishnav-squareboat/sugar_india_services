import { useEffect, useState } from "react";
import axios from "axios";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Phone, Mail, Globe, MapPin, Star, Linkedin, Cpu, Zap, Copy, Check, RefreshCw } from "lucide-react";

const API = `${import.meta.env.VITE_BACKEND_URL}/api`;

const segColor = (s) => ({
  Hotel: "#143628", Restaurant: "#3D6B56", Cafe: "#8FA39A",
  // Bakery: "#B85C38", CloudKitchen: "#D4956A", Catering: "#6B5E44",
  // Mithai: "#A0522D", IceCream: "#C4878A"
}[s] || "#5C736A");

const STATUSES = ["new", "contacted", "qualified", "converted", "lost"];

function ScoreGauge({ score }) {
  const color = score >= 70 ? "#143628" : score >= 40 ? "#B85C38" : "#9CA3AF";
  const label = score >= 70 ? "High Priority" : score >= 40 ? "Medium Priority" : "Low Priority";
  return (
    <div className="text-center">
      <div className="relative inline-flex items-center justify-center w-28 h-28 mx-auto mb-2">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="52" fill="none" stroke="#EDF0EA" strokeWidth="12" />
          <circle
            cx="60" cy="60" r="52" fill="none" stroke={color} strokeWidth="12"
            strokeDasharray={`${(score / 100) * 327} 327`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.8s ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color, fontFamily: 'Plus Jakarta Sans, sans-serif' }}>{score}</span>
          <span className="text-xs text-[#5C736A]">/100</span>
        </div>
      </div>
      <span className="text-xs font-semibold px-3 py-1 rounded-full" style={{ backgroundColor: color + '18', color }}>{label}</span>
    </div>
  );
}

function ScoreItem({ text }) {
  const parts = text.split('(+');
  const pts = parts[1] ? '+' + parts[1] : '';
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[#F4F5F0] last:border-0">
      <span className="text-xs text-[#5C736A]">{parts[0].trim()}</span>
      {pts && <span className="text-xs font-semibold text-[#143628]">+{pts.replace(')', '')}</span>}
    </div>
  );
}

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [qualifying, setQualifying] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(null);
  const [activeEmail, setActiveEmail] = useState(null);

  const fetchData = async () => {
    const [leadRes, emailRes] = await Promise.all([
      axios.get(`${API}/leads/${id}`),
      axios.get(`${API}/outreach/${id}/emails`)
    ]);
    setLead(leadRes.data);
    setEmails(emailRes.data);
    if (emailRes.data.length > 0) setActiveEmail(emailRes.data[0]);
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [id]);

  const handleQualify = async () => {
    setQualifying(true);
    try {
      const res = await axios.post(`${API}/leads/${id}/qualify-ai`);
      setLead(res.data.lead);
      setAiAnalysis(res.data.ai_analysis);
    } catch (err) {
      alert("AI qualification failed. Check API key or try again.");
    }
    setQualifying(false);
  };

  const handleGenerateEmail = async () => {
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/leads/${id}/generate-email`);
      setEmails(prev => [res.data, ...prev]);
      setActiveEmail(res.data);
    } catch (err) {
      alert("Email generation failed. Check API key.");
    }
    setGenerating(false);
  };

  const handleStatusChange = async (status) => {
    const res = await axios.put(`${API}/leads/${id}/status`, { status });
    setLead(res.data);
  };

  const copyEmail = (content) => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const markSent = async (emailId) => {
    await axios.put(`${API}/outreach/${emailId}/mark-sent`);
    fetchData();
  };

  if (loading) {
    return (
      <div className="p-6 animate-pulse">
        <div className="h-6 bg-[#EAECE6] rounded w-40 mb-6" />
        <div className="grid grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <div key={i} className="h-64 bg-[#EAECE6] rounded-lg" />)}
        </div>
      </div>
    );
  }

  if (!lead) return <div className="p-6 text-[#5C736A]">Lead not found.</div>;

  const scoreItems = lead.ai_reasoning?.split(' | ') || [];

  return (
    <div className="p-6 animate-fade-in" style={{ backgroundColor: "#F8F9F6", minHeight: "100vh" }}>
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-3">
          <button
            data-testid="back-btn"
            onClick={() => navigate("/leads")}
            className="p-2 rounded-lg border border-[#DCE1D9] bg-white hover:bg-[#EAECE6] transition-colors"
          >
            <ArrowLeft size={16} className="text-[#5C736A]" />
          </button>
          <div>
            <p className="text-xs uppercase tracking-widest text-[#5C736A]" style={{ letterSpacing: '0.15em' }}>Lead Detail</p>
            <h1 className="text-xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
              {lead.business_name}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <select
            data-testid="lead-status-select"
            value={lead.status}
            onChange={e => handleStatusChange(e.target.value)}
            className="border border-[#DCE1D9] rounded-md px-3 py-1.5 text-sm bg-white text-[#16221E] focus:outline-none focus:ring-1 focus:ring-[#143628]"
          >
            {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
        </div>
      </div>

      {/* 3-column bento grid */}
      <div className="grid grid-cols-3 gap-4">
        {/* LEFT: Contact info */}
        <div className="space-y-4">
          {/* Business card */}
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="px-2 py-0.5 rounded text-xs text-white font-medium" style={{ backgroundColor: segColor(lead.segment) }}>
                {lead.segment}
              </span>
              {lead.hotel_category && (
                <span className="px-2 py-0.5 rounded text-xs bg-[#EDF0EA] text-[#143628]">{lead.hotel_category}</span>
              )}
              {lead.is_chain && <span className="px-2 py-0.5 rounded text-xs bg-[#EDF0EA] text-[#5C736A]">Chain</span>}
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <MapPin size={14} className="text-[#5C736A] mt-0.5 flex-shrink-0" />
                <span className="text-[#16221E]">{lead.city}, {lead.state} <span className="text-[#9CA3AF]">(Tier {lead.tier})</span></span>
              </div>
              {lead.address && (
                <div className="flex items-start gap-2">
                  <MapPin size={14} className="text-[#DCE1D9] mt-0.5 flex-shrink-0" />
                  <span className="text-[#5C736A] text-xs">{lead.address}</span>
                </div>
              )}
              {lead.phone && (
                <div className="flex items-center gap-2">
                  <Phone size={14} className="text-[#5C736A]" />
                  <a href={`tel:${lead.phone}`} className="text-[#143628] hover:underline">{lead.phone}</a>
                </div>
              )}
              {lead.email && (
                <div className="flex items-center gap-2">
                  <Mail size={14} className="text-[#5C736A]" />
                  <a href={`mailto:${lead.email}`} className="text-[#143628] hover:underline text-xs truncate">{lead.email}</a>
                </div>
              )}
              {lead.website && (
                <div className="flex items-center gap-2">
                  <Globe size={14} className="text-[#5C736A]" />
                  <a href={`https://${lead.website}`} target="_blank" rel="noreferrer" className="text-[#143628] hover:underline text-xs truncate">{lead.website}</a>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 mt-4 pt-3 border-t border-[#F4F5F0]">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <Star size={12} className="text-amber-400 fill-amber-400" />
                  <span className="font-bold text-[#16221E]">{lead.rating}</span>
                </div>
                <p className="text-xs text-[#9CA3AF]">Rating</p>
              </div>
              <div className="text-center">
                <p className="font-bold text-[#16221E]">{lead.num_outlets}</p>
                <p className="text-xs text-[#9CA3AF]">Outlets</p>
              </div>
            </div>
          </div>

          {/* Decision Maker */}
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-4">
            <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-3" style={{ letterSpacing: '0.15em' }}>Decision Maker</p>
            {lead.decision_maker_name ? (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-[#EDF0EA] flex items-center justify-center text-sm font-bold text-[#143628]">
                    {lead.decision_maker_name.charAt(0)}
                  </div>
                  <div>
                    <p className="font-medium text-sm text-[#16221E]">{lead.decision_maker_name}</p>
                    <p className="text-xs text-[#5C736A]">{lead.decision_maker_role}</p>
                  </div>
                </div>
                {lead.decision_maker_linkedin && (
                  <a
                    href={`https://${lead.decision_maker_linkedin}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 text-xs text-[#143628] hover:opacity-70"
                  >
                    <Linkedin size={13} /> View LinkedIn Profile
                  </a>
                )}
              </div>
            ) : (
              <p className="text-sm text-[#9CA3AF]">No contact info available</p>
            )}
          </div>

          {/* Volume estimate */}
          {lead.monthly_volume_estimate && (
            <div className="bg-[#143628] rounded-xl p-4 text-white">
              <p className="text-xs uppercase tracking-widest text-white/50 mb-1" style={{ letterSpacing: '0.15em' }}>Est. Monthly Volume</p>
              <p className="text-xl font-bold" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>{lead.monthly_volume_estimate}</p>
              <p className="text-xs text-white/50 mt-1">Sugar/sweetener consumption</p>
            </div>
          )}

          {lead.has_dessert_menu && (
            <div className="bg-[#B85C38]/10 border border-[#B85C38]/20 rounded-xl p-3">
              <p className="text-xs font-semibold text-[#B85C38]">Has Dessert/Sweet Menu</p>
              <p className="text-xs text-[#B85C38]/70 mt-0.5">High sugar consumption potential</p>
            </div>
          )}
        </div>

        {/* CENTER: AI Score + Reasoning */}
        <div className="space-y-4">
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-5">
            <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-4" style={{ letterSpacing: '0.15em' }}>AI Lead Score</p>
            <ScoreGauge score={lead.ai_score} />

            <div className="mt-5">
              <p className="text-xs font-semibold text-[#16221E] mb-2">Scoring Breakdown</p>
              <div className="space-y-0">
                {scoreItems.map((item, i) => <ScoreItem key={i} text={item} />)}
              </div>
            </div>

            <button
              data-testid="qualify-ai-btn"
              onClick={handleQualify}
              disabled={qualifying}
              className="w-full mt-4 flex items-center justify-center gap-2 py-2.5 rounded-lg text-white text-sm font-medium disabled:opacity-60 hover:opacity-90 transition-opacity"
              style={{ backgroundColor: "#B85C38" }}
            >
              {qualifying ? (
                <><RefreshCw size={15} className="animate-spin" /> Qualifying with AI...</>
              ) : (
                <><Cpu size={15} /> Re-qualify with AI</>
              )}
            </button>
          </div>

          {/* AI Analysis Result */}
          {aiAnalysis && (
            <div className="bg-white border border-[#143628]/20 rounded-xl p-4 animate-fade-in" data-testid="ai-analysis-result">
              <p className="text-xs uppercase tracking-widest text-[#143628] mb-3" style={{ letterSpacing: '0.15em' }}>AI Analysis</p>
              <p className="text-sm text-[#16221E] mb-3">{aiAnalysis.qualification_summary}</p>
              {aiAnalysis.sugar_use_cases?.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-semibold text-[#5C736A] mb-1">Sugar Use Cases</p>
                  <ul className="space-y-1">
                    {aiAnalysis.sugar_use_cases.map((uc, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-xs text-[#5C736A]">
                        <span className="text-[#B85C38] mt-0.5">•</span> {uc}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {aiAnalysis.key_insight && (
                <div className="bg-[#EDF0EA] rounded-lg p-3">
                  <p className="text-xs font-semibold text-[#143628] mb-0.5">Key Insight</p>
                  <p className="text-xs text-[#5C736A]">{aiAnalysis.key_insight}</p>
                </div>
              )}
              {aiAnalysis.best_contact_time && (
                <p className="text-xs text-[#5C736A] mt-2">Best contact time: {aiAnalysis.best_contact_time}</p>
              )}
            </div>
          )}

          {lead.ai_reasoning && !aiAnalysis && (
            <div className="bg-white border border-[#DCE1D9] rounded-xl p-4">
              <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-2" style={{ letterSpacing: '0.15em' }}>Qualification Summary</p>
              <p className="text-sm text-[#5C736A]">{lead.ai_reasoning}</p>
            </div>
          )}
        </div>

        {/* RIGHT: Outreach Emails */}
        <div className="space-y-4">
          <div className="bg-white border border-[#DCE1D9] rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs uppercase tracking-widest text-[#5C736A]" style={{ letterSpacing: '0.15em' }}>Outreach Emails</p>
              <span className="text-xs bg-[#EDF0EA] text-[#5C736A] px-2 py-0.5 rounded-full">{emails.length}</span>
            </div>

            <button
              data-testid="generate-email-btn"
              onClick={handleGenerateEmail}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-white text-sm font-medium disabled:opacity-60 hover:opacity-90 transition-opacity mb-4"
              style={{ backgroundColor: generating ? "#5C736A" : "#B85C38" }}
            >
              {generating ? (
                <><RefreshCw size={15} className="animate-spin" /> Generating Email...</>
              ) : (
                <><Zap size={15} /> Generate AI Email</>
              )}
            </button>

            {emails.length > 0 && (
              <div className="space-y-2">
                {emails.map((email, i) => (
                  <button
                    key={email.id}
                    data-testid={`email-item-${i}`}
                    onClick={() => setActiveEmail(email)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${activeEmail?.id === email.id ? "border-[#143628] bg-[#143628]/5" : "border-[#DCE1D9] hover:bg-[#F8F9F6]"}`}
                  >
                    <p className="text-xs font-medium text-[#16221E] truncate">{email.subject || "No subject"}</p>
                    <div className="flex items-center justify-between mt-1">
                      <p className="text-xs text-[#9CA3AF]">{new Date(email.generated_at).toLocaleDateString('en-IN')}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${email.status === 'sent' ? "bg-green-100 text-green-700" : "bg-[#EDF0EA] text-[#5C736A]"}`}>
                        {email.status}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Active Email Preview */}
          {activeEmail && (
            <div className="bg-white border border-[#DCE1D9] rounded-xl p-4" data-testid="email-preview">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold text-[#16221E] truncate flex-1">{activeEmail.subject}</p>
                <div className="flex gap-2 ml-2 flex-shrink-0">
                  <button
                    data-testid="copy-email-btn"
                    onClick={() => copyEmail(`Subject: ${activeEmail.subject}\n\n${activeEmail.body}`)}
                    className="p-1.5 rounded-md border border-[#DCE1D9] hover:bg-[#EDF0EA] transition-colors"
                    title="Copy email"
                  >
                    {copied ? <Check size={13} className="text-green-600" /> : <Copy size={13} className="text-[#5C736A]" />}
                  </button>
                  {activeEmail.status === 'draft' && (
                    <button
                      data-testid="mark-sent-btn"
                      onClick={() => markSent(activeEmail.id)}
                      className="px-2.5 py-1 rounded-md text-xs font-medium text-white bg-[#143628] hover:opacity-90"
                    >
                      Mark Sent
                    </button>
                  )}
                </div>
              </div>
              <div className="email-editor text-xs">{activeEmail.body}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
