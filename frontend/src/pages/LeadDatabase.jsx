import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Search, Filter, ChevronUp, ChevronDown, MapPin, Star, Trash2, ExternalLink } from "lucide-react";

const API = `${import.meta.env.VITE_BACKEND_URL}/api`;

const SEGMENTS = ["", "Hotel", "Restaurant", "Cafe", "Bakery", "CloudKitchen", "Catering", "Mithai", "IceCream"];
const PRIORITIES = ["", "High", "Medium", "Low"];
const STATUSES = ["", "new", "contacted", "qualified", "converted", "lost"];

const segColor = (s) => ({
  Hotel: "#143628", Restaurant: "#3D6B56", Cafe: "#8FA39A",
  Bakery: "#B85C38", CloudKitchen: "#D4956A", Catering: "#6B5E44",
  Mithai: "#A0522D", IceCream: "#C4878A"
}[s] || "#5C736A");

const priorityBg = (p) => p === "High" ? "badge-high" : p === "Medium" ? "badge-medium" : "badge-low";

const statusColors = {
  new: { bg: "#EDF0EA", text: "#5C736A" },
  contacted: { bg: "rgba(20,54,40,0.1)", text: "#143628" },
  qualified: { bg: "rgba(184,92,56,0.1)", text: "#B85C38" },
  converted: { bg: "rgba(22,163,74,0.1)", text: "#16a34a" },
  lost: { bg: "rgba(156,163,175,0.15)", text: "#6B7280" }
};

function ScoreBar({ score }) {
  const color = score >= 70 ? "#143628" : score >= 40 ? "#B85C38" : "#9CA3AF";
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 bg-[#EDF0EA] rounded-full overflow-hidden">
        <div className="h-full rounded-full score-bar-fill" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-bold w-6 text-right" style={{ color }}>{score}</span>
    </div>
  );
}

export default function LeadDatabase() {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ city: "", segment: "", priority: "", status: "", min_score: "" });
  const [showFilters, setShowFilters] = useState(false);
  const [sortField, setSortField] = useState("ai_score");
  const [sortDir, setSortDir] = useState("desc");
  const navigate = useNavigate();

  const fetchLeads = async () => {
    setLoading(true);
    const params = { search, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")) };
    const res = await axios.get(`${API}/leads`, { params });
    let data = res.data.leads || [];
    // Client-side sort
    data = data.sort((a, b) => {
      let av = a[sortField], bv = b[sortField];
      if (typeof av === 'string') { av = av.toLowerCase(); bv = bv.toLowerCase(); }
      return sortDir === "asc" ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });
    setLeads(data);
    setTotal(res.data.total || data.length);
    setLoading(false);
  };

  useEffect(() => { fetchLeads(); }, [search, filters, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("desc"); }
  };

  const updateStatus = async (e, leadId, status) => {
    e.stopPropagation();
    await axios.put(`${API}/leads/${leadId}/status`, { status });
    fetchLeads();
  };

  const deleteLead = async (e, leadId) => {
    e.stopPropagation();
    if (!window.confirm("Delete this lead?")) return;
    await axios.delete(`${API}/leads/${leadId}`);
    fetchLeads();
  };

  const setFilter = (k, v) => setFilters(f => ({ ...f, [k]: v }));
  const clearFilters = () => setFilters({ city: "", segment: "", priority: "", status: "", min_score: "" });

  const SortIcon = ({ field }) => sortField === field
    ? (sortDir === "asc" ? <ChevronUp size={13} /> : <ChevronDown size={13} />)
    : <ChevronDown size={13} className="opacity-30" />;

  const inputClass = "border border-[#DCE1D9] rounded-md px-3 py-1.5 text-sm bg-white text-[#16221E] focus:outline-none focus:ring-1 focus:ring-[#143628]";

  return (
    <div className="p-6" style={{ backgroundColor: "#F8F9F6", minHeight: "100vh" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5 animate-fade-in">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-1" style={{ letterSpacing: '0.2em' }}>All Leads</p>
          <h1 className="text-2xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
            Lead Database
            <span className="ml-3 text-sm font-normal text-[#5C736A] bg-[#EDF0EA] px-2 py-0.5 rounded-full">{total}</span>
          </h1>
        </div>
        <button
          data-testid="toggle-filters-btn"
          onClick={() => setShowFilters(f => !f)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[#DCE1D9] text-sm text-[#5C736A] hover:bg-[#EAECE6] transition-colors"
        >
          <Filter size={14} /> Filters {showFilters ? "▲" : "▼"}
        </button>
      </div>

      {/* Search + Filters */}
      <div className="bg-white border border-[#DCE1D9] rounded-xl p-4 mb-4 animate-fade-in animate-fade-in-delay-1">
        <div className="flex gap-3 items-center mb-3">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#5C736A]" />
            <input
              data-testid="lead-search-input"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by name, city, decision maker..."
              className="w-full pl-9 border border-[#DCE1D9] rounded-md py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-[#143628]"
            />
          </div>
          {Object.values(filters).some(v => v) && (
            <button onClick={clearFilters} className="text-xs text-[#B85C38] hover:opacity-70 whitespace-nowrap" data-testid="clear-filters-btn">Clear filters</button>
          )}
        </div>

        {showFilters && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 pt-3 border-t border-[#EDF0EA]" data-testid="filter-panel">
            <div>
              <label className="text-xs text-[#5C736A] mb-1 block">City</label>
              <input value={filters.city} onChange={e => setFilter('city', e.target.value)} placeholder="Any city" className={inputClass + " w-full"} data-testid="filter-city" />
            </div>
            <div>
              <label className="text-xs text-[#5C736A] mb-1 block">Segment</label>
              <select value={filters.segment} onChange={e => setFilter('segment', e.target.value)} className={inputClass + " w-full"} data-testid="filter-segment">
                {SEGMENTS.map(s => <option key={s} value={s}>{s || "All Segments"}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[#5C736A] mb-1 block">Priority</label>
              <select value={filters.priority} onChange={e => setFilter('priority', e.target.value)} className={inputClass + " w-full"} data-testid="filter-priority">
                {PRIORITIES.map(p => <option key={p} value={p}>{p || "All Priorities"}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[#5C736A] mb-1 block">Status</label>
              <select value={filters.status} onChange={e => setFilter('status', e.target.value)} className={inputClass + " w-full"} data-testid="filter-status">
                {STATUSES.map(s => <option key={s} value={s}>{s || "All Statuses"}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[#5C736A] mb-1 block">Min Score</label>
              <input type="number" min={0} max={100} value={filters.min_score} onChange={e => setFilter('min_score', e.target.value)} placeholder="0" className={inputClass + " w-full"} data-testid="filter-min-score" />
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-[#DCE1D9] rounded-xl overflow-hidden animate-fade-in animate-fade-in-delay-2">
        {loading ? (
          <div className="p-8 text-center text-[#5C736A] text-sm">Loading leads...</div>
        ) : leads.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-[#5C736A] text-sm">No leads found. Try adjusting your filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="leads-table">
              <thead>
                <tr className="border-b border-[#EDF0EA] bg-[#F8F9F6]">
                  {[
                    { label: "Business", field: "business_name" },
                    { label: "Location", field: "city" },
                    { label: "AI Score", field: "ai_score" },
                    { label: "Priority", field: "priority" },
                    { label: "Status", field: "status" },
                    { label: "Decision Maker", field: "decision_maker_name" },
                    { label: "Rating", field: "rating" },
                    { label: "", field: null }
                  ].map(({ label, field }) => (
                    <th
                      key={label}
                      onClick={() => field && toggleSort(field)}
                      className={`px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[#5C736A] whitespace-nowrap ${field ? "cursor-pointer hover:text-[#143628]" : ""}`}
                      style={{ letterSpacing: '0.08em' }}
                    >
                      <span className="flex items-center gap-1">{label} {field && <SortIcon field={field} />}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leads.map((lead, i) => (
                  <tr
                    key={lead.id}
                    data-testid={`lead-row-${i}`}
                    className="lead-row border-b border-[#F4F5F0] last:border-0"
                    onClick={() => navigate(`/leads/${lead.id}`)}
                  >
                    <td className="px-3 py-3">
                      <div>
                        <p className="font-medium text-[#16221E] truncate max-w-[200px]">{lead.business_name}</p>
                        <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded text-xs text-white" style={{ backgroundColor: segColor(lead.segment) }}>
                          {lead.segment}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 text-[#5C736A]">
                        <MapPin size={11} />
                        <span>{lead.city}</span>
                      </div>
                      <span className="text-xs text-[#9CA3AF]">Tier {lead.tier}</span>
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={lead.ai_score} />
                    </td>
                    <td className="px-3 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${priorityBg(lead.priority)}`}>
                        {lead.priority}
                      </span>
                    </td>
                    <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                      <select
                        data-testid={`status-select-${i}`}
                        value={lead.status}
                        onChange={e => updateStatus(e, lead.id, e.target.value)}
                        className="text-xs border-none rounded px-2 py-1 cursor-pointer focus:outline-none"
                        style={{ backgroundColor: statusColors[lead.status]?.bg || "#EDF0EA", color: statusColors[lead.status]?.text || "#5C736A" }}
                      >
                        {STATUSES.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      {lead.decision_maker_name ? (
                        <div>
                          <p className="text-xs text-[#16221E]">{lead.decision_maker_name}</p>
                          <p className="text-xs text-[#9CA3AF]">{lead.decision_maker_role}</p>
                        </div>
                      ) : <span className="text-xs text-[#9CA3AF]">—</span>}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1">
                        <Star size={11} className="text-amber-400 fill-amber-400" />
                        <span className="text-xs text-[#5C736A]">{lead.rating || "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <button
                          data-testid={`view-lead-btn-${i}`}
                          onClick={() => navigate(`/leads/${lead.id}`)}
                          className="p-1 rounded hover:bg-[#EDF0EA] text-[#5C736A]"
                          title="View"
                        >
                          <ExternalLink size={14} />
                        </button>
                        <button
                          data-testid={`delete-lead-btn-${i}`}
                          onClick={e => deleteLead(e, lead.id)}
                          className="p-1 rounded hover:bg-red-50 text-[#9CA3AF] hover:text-red-500"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
