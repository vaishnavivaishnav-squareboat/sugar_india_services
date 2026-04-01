import { useState, useRef } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Search, Upload, PlusCircle, CheckSquare, Square, ArrowRight, ChevronDown, Download } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEGMENTS = ["Hotel", "Restaurant", "Cafe", "Bakery", "CloudKitchen", "Catering", "Mithai", "IceCream"];
const CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad",
  "Jaipur", "Lucknow", "Surat", "Chandigarh", "Nagpur", "Indore", "Bhopal", "Visakhapatnam", "Coimbatore"];
const STATES = {
  "Mumbai": "Maharashtra", "Delhi": "Delhi", "Bangalore": "Karnataka", "Hyderabad": "Telangana",
  "Chennai": "Tamil Nadu", "Kolkata": "West Bengal", "Pune": "Maharashtra", "Ahmedabad": "Gujarat",
  "Jaipur": "Rajasthan", "Lucknow": "Uttar Pradesh", "Surat": "Gujarat", "Chandigarh": "Punjab",
  "Nagpur": "Maharashtra", "Indore": "Madhya Pradesh", "Bhopal": "Madhya Pradesh"
};

const priorityColor = (p) => p === "High" ? "#B85C38" : p === "Medium" ? "#143628" : "#5C736A";
const segColor = (s) => ({ Hotel: "#143628", Restaurant: "#3D6B56", Cafe: "#8FA39A", Bakery: "#B85C38", CloudKitchen: "#D4956A", Catering: "#6B5E44", Mithai: "#A0522D", IceCream: "#C4878A" }[s] || "#5C736A");

function ScoreBar({ score }) {
  const color = score >= 70 ? "#143628" : score >= 40 ? "#B85C38" : "#9CA3AF";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#EDF0EA] rounded-full overflow-hidden" style={{ minWidth: 60 }}>
        <div className="h-full rounded-full" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-semibold" style={{ color }}>{score}</span>
    </div>
  );
}

function TabButton({ active, onClick, children, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${active ? "border-[#143628] text-[#143628]" : "border-transparent text-[#5C736A] hover:text-[#16221E]"}`}
    >
      {children}
    </button>
  );
}

// ─── Discover Tab ─────────────────────────────────────────────────────────────
function DiscoverTab() {
  const [city, setCity] = useState("Mumbai");
  const [segment, setSegment] = useState("Hotel");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();

  const handleSearch = async () => {
    setLoading(true);
    setSaved(false);
    setSelected(new Set());
    try {
      const res = await axios.post(`${API}/leads/discover`, { city, segment, state: STATES[city] || "" });
      setResults(res.data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const toggleSelect = (i) => {
    const s = new Set(selected);
    s.has(i) ? s.delete(i) : s.add(i);
    setSelected(s);
  };

  const selectAll = () => setSelected(new Set(results.map((_, i) => i)));
  const clearAll = () => setSelected(new Set());

  const handleSave = async () => {
    const toSave = results.filter((_, i) => selected.has(i));
    await axios.post(`${API}/leads/bulk-create`, { leads: toSave });
    setSaved(true);
    setTimeout(() => navigate("/leads"), 1200);
  };

  return (
    <div className="space-y-5">
      <div className="bg-[#EAECE6] rounded-lg p-5 border border-dashed border-[#DCE1D9]">
        <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-3" style={{ letterSpacing: '0.15em' }}>
          Search HORECA Leads
        </p>
        <div className="flex gap-3 items-end flex-wrap">
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs text-[#5C736A] mb-1 block">City</label>
            <select
              data-testid="discover-city-select"
              value={city}
              onChange={e => setCity(e.target.value)}
              className="w-full border border-[#DCE1D9] rounded-md px-3 py-2 text-sm bg-white text-[#16221E] focus:outline-none focus:ring-1 focus:ring-[#143628]"
            >
              {CITIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs text-[#5C736A] mb-1 block">Segment</label>
            <select
              data-testid="discover-segment-select"
              value={segment}
              onChange={e => setSegment(e.target.value)}
              className="w-full border border-[#DCE1D9] rounded-md px-3 py-2 text-sm bg-white text-[#16221E] focus:outline-none focus:ring-1 focus:ring-[#143628]"
            >
              {SEGMENTS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button
            data-testid="discover-search-btn"
            onClick={handleSearch}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2 rounded-md text-white text-sm font-medium disabled:opacity-60 transition-opacity hover:opacity-90"
            style={{ backgroundColor: "#143628" }}
          >
            <Search size={15} />
            {loading ? "Searching..." : "Search Leads"}
          </button>
        </div>
        <p className="text-xs text-[#5C736A] mt-3 flex items-center gap-1">
          Simulates Google Maps + Zomato discovery for {segment}s in {city}
        </p>
      </div>

      {results.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-medium text-[#16221E]">{results.length} leads found in {city}</p>
            <div className="flex gap-2">
              <button onClick={selectAll} className="text-xs text-[#143628] hover:opacity-70"
                data-testid="select-all-btn">Select All</button>
              <span className="text-[#DCE1D9]">|</span>
              <button onClick={clearAll} className="text-xs text-[#5C736A] hover:opacity-70">Clear</button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            {results.map((lead, i) => (
              <div
                key={i}
                data-testid={`discover-result-${i}`}
                onClick={() => toggleSelect(i)}
                className={`bg-white border rounded-lg p-4 cursor-pointer transition-all ${selected.has(i) ? "border-[#143628] ring-1 ring-[#143628]" : "border-[#DCE1D9]"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {selected.has(i) ? <CheckSquare size={16} className="text-[#143628] flex-shrink-0" /> : <Square size={16} className="text-[#DCE1D9] flex-shrink-0" />}
                      <p className="font-semibold text-sm text-[#16221E] truncate">{lead.business_name}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      <span className="px-2 py-0.5 rounded text-xs font-medium text-white" style={{ backgroundColor: segColor(lead.segment) }}>
                        {lead.segment}
                      </span>
                      {lead.hotel_category && (
                        <span className="px-2 py-0.5 rounded text-xs bg-[#EDF0EA] text-[#143628]">{lead.hotel_category}</span>
                      )}
                      {lead.is_chain && <span className="px-2 py-0.5 rounded text-xs bg-[#EDF0EA] text-[#5C736A]">Chain</span>}
                    </div>
                    <div className="mt-2 text-xs text-[#5C736A] space-y-0.5">
                      <p>{lead.num_outlets} outlet(s) · Rating {lead.rating}/5</p>
                      <p>{lead.decision_maker_name} · {lead.decision_maker_role}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold" style={{ color: lead.ai_score >= 70 ? "#143628" : lead.ai_score >= 40 ? "#B85C38" : "#9CA3AF", fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
                      {lead.ai_score}
                    </div>
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: priorityColor(lead.priority) + '18', color: priorityColor(lead.priority) }}>
                      {lead.priority}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {selected.size > 0 && (
            <button
              data-testid="save-selected-leads-btn"
              onClick={handleSave}
              className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-white text-sm font-medium transition-opacity hover:opacity-90"
              style={{ backgroundColor: saved ? "#16a34a" : "#B85C38" }}
            >
              {saved ? "Saved! Redirecting..." : `Save ${selected.size} Selected Leads`}
              {!saved && <ArrowRight size={15} />}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── CSV Upload Tab ───────────────────────────────────────────────────────────
function CSVTab() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith('.csv')) setFile(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await axios.post(`${API}/leads/upload-csv`, form);
      setResult(res.data);
    } catch (e) {
      setResult({ error: e.message });
    }
    setUploading(false);
  };

  const downloadTemplate = () => {
    window.open(`${API}/leads/csv-template`, '_blank');
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[#5C736A]">Upload a CSV file with your HORECA leads</p>
        <button
          data-testid="download-template-btn"
          onClick={downloadTemplate}
          className="flex items-center gap-1.5 text-sm text-[#143628] hover:opacity-70 font-medium border border-[#DCE1D9] px-3 py-1.5 rounded-md"
        >
          <Download size={13} /> Download Template
        </button>
      </div>

      <div
        data-testid="csv-dropzone"
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${dragOver ? "border-[#143628] bg-[#143628]/5" : "border-[#DCE1D9] bg-[#EAECE6] hover:border-[#143628]/40"}`}
        style={{
          backgroundImage: `url(https://images.unsplash.com/photo-1751956066306-c5684cbcf385?w=600&q=40)`,
          backgroundSize: 'cover', backgroundPosition: 'center', backgroundBlendMode: 'overlay'
        }}
      >
        <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={e => setFile(e.target.files[0])} />
        <Upload size={32} className="mx-auto mb-3 text-[#143628] opacity-70" strokeWidth={1.5} />
        {file ? (
          <div>
            <p className="font-semibold text-[#143628]">{file.name}</p>
            <p className="text-sm text-[#5C736A] mt-1">{(file.size / 1024).toFixed(1)} KB · Ready to upload</p>
          </div>
        ) : (
          <div>
            <p className="font-semibold text-[#16221E]">Drop CSV file here or click to browse</p>
            <p className="text-sm text-[#5C736A] mt-1">Supports .csv format</p>
          </div>
        )}
      </div>

      {file && (
        <button
          data-testid="upload-csv-btn"
          onClick={handleUpload}
          disabled={uploading}
          className="px-6 py-2.5 rounded-lg text-white text-sm font-medium disabled:opacity-60 hover:opacity-90 transition-opacity"
          style={{ backgroundColor: "#143628" }}
        >
          {uploading ? "Uploading..." : "Upload & Import Leads"}
        </button>
      )}

      {result && (
        <div data-testid="upload-result" className={`p-4 rounded-lg border ${result.error ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"}`}>
          {result.error ? (
            <p className="text-red-700 text-sm">{result.error}</p>
          ) : (
            <div>
              <p className="font-semibold text-green-800">{result.created} leads imported successfully</p>
              {result.errors?.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-red-600 font-medium">{result.errors.length} errors:</p>
                  {result.errors.slice(0, 3).map((e, i) => <p key={i} className="text-xs text-red-500">{e}</p>)}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* CSV Format guide */}
      <div className="bg-white border border-[#DCE1D9] rounded-lg p-4">
        <p className="text-xs font-semibold text-[#143628] uppercase tracking-widest mb-3" style={{ letterSpacing: '0.1em' }}>CSV Column Guide</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          {[
            ["business_name*", "Business name"],
            ["city*", "City name"],
            ["segment", "Hotel/Restaurant/Cafe/Bakery..."],
            ["tier", "1=Metro, 2=Tier2, 3=Tier3"],
            ["rating", "0.0 to 5.0"],
            ["num_outlets", "Number of outlets"],
            ["hotel_category", "3-star/4-star/5-star"],
            ["is_chain", "true/false"],
            ["has_dessert_menu", "true/false"],
            ["decision_maker_name", "Contact person name"],
          ].map(([col, desc]) => (
            <div key={col} className="flex gap-2">
              <code className="text-xs text-[#B85C38] font-mono">{col}</code>
              <span className="text-xs text-[#5C736A]">— {desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Manual Entry Tab ─────────────────────────────────────────────────────────
function ManualTab() {
  const [form, setForm] = useState({
    business_name: "", segment: "Restaurant", city: "", state: "",
    tier: 1, address: "", phone: "", email: "", website: "",
    rating: 0, num_outlets: 1, decision_maker_name: "", decision_maker_role: "",
    decision_maker_linkedin: "", has_dessert_menu: false, hotel_category: "",
    is_chain: false, monthly_volume_estimate: ""
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`${API}/leads`, form);
      setSaved(true);
      setTimeout(() => navigate("/leads"), 1200);
    } catch (err) { console.error(err); }
    setSaving(false);
  };

  const inputClass = "w-full border border-[#DCE1D9] rounded-md px-3 py-2 text-sm bg-white text-[#16221E] focus:outline-none focus:ring-1 focus:ring-[#143628]";
  const labelClass = "text-xs text-[#5C736A] mb-1 block";

  return (
    <form onSubmit={handleSubmit} className="space-y-5" data-testid="manual-entry-form">
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2 md:col-span-1">
          <label className={labelClass}>Business Name *</label>
          <input data-testid="manual-business-name" required value={form.business_name} onChange={e => set('business_name', e.target.value)} className={inputClass} placeholder="e.g. The Grand Palace Hotel" />
        </div>
        <div>
          <label className={labelClass}>Segment</label>
          <select data-testid="manual-segment" value={form.segment} onChange={e => set('segment', e.target.value)} className={inputClass}>
            {SEGMENTS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>City *</label>
          <input data-testid="manual-city" required value={form.city} onChange={e => { set('city', e.target.value); set('state', STATES[e.target.value] || form.state); }} list="cities-list" className={inputClass} placeholder="Mumbai" />
          <datalist id="cities-list">{CITIES.map(c => <option key={c} value={c} />)}</datalist>
        </div>
        <div>
          <label className={labelClass}>State</label>
          <input value={form.state} onChange={e => set('state', e.target.value)} className={inputClass} placeholder="Maharashtra" />
        </div>
        <div>
          <label className={labelClass}>City Tier</label>
          <select value={form.tier} onChange={e => set('tier', Number(e.target.value))} className={inputClass}>
            <option value={1}>Tier 1 (Metro)</option>
            <option value={2}>Tier 2</option>
            <option value={3}>Tier 3</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Rating (0-5)</label>
          <input type="number" min={0} max={5} step={0.1} value={form.rating} onChange={e => set('rating', parseFloat(e.target.value))} className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Number of Outlets</label>
          <input type="number" min={1} value={form.num_outlets} onChange={e => set('num_outlets', parseInt(e.target.value))} className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Hotel Category</label>
          <select value={form.hotel_category} onChange={e => set('hotel_category', e.target.value)} className={inputClass}>
            <option value="">N/A</option>
            <option value="3-star">3-star</option>
            <option value="4-star">4-star</option>
            <option value="5-star">5-star</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Phone</label>
          <input value={form.phone} onChange={e => set('phone', e.target.value)} className={inputClass} placeholder="+91-9876543210" />
        </div>
        <div>
          <label className={labelClass}>Email</label>
          <input type="email" value={form.email} onChange={e => set('email', e.target.value)} className={inputClass} placeholder="procurement@hotel.com" />
        </div>
        <div>
          <label className={labelClass}>Decision Maker Name</label>
          <input value={form.decision_maker_name} onChange={e => set('decision_maker_name', e.target.value)} className={inputClass} placeholder="Rajesh Kumar" />
        </div>
        <div>
          <label className={labelClass}>Decision Maker Role</label>
          <input value={form.decision_maker_role} onChange={e => set('decision_maker_role', e.target.value)} className={inputClass} placeholder="Procurement Manager" />
        </div>
        <div className="col-span-2">
          <label className={labelClass}>LinkedIn URL</label>
          <input value={form.decision_maker_linkedin} onChange={e => set('decision_maker_linkedin', e.target.value)} className={inputClass} placeholder="linkedin.com/in/rajesh-kumar" />
        </div>
        <div className="flex items-center gap-3">
          <input type="checkbox" id="dessert" checked={form.has_dessert_menu} onChange={e => set('has_dessert_menu', e.target.checked)} className="w-4 h-4 accent-[#143628]" />
          <label htmlFor="dessert" className="text-sm text-[#16221E]">Has Dessert/Sweet Menu</label>
        </div>
        <div className="flex items-center gap-3">
          <input type="checkbox" id="chain" checked={form.is_chain} onChange={e => set('is_chain', e.target.checked)} className="w-4 h-4 accent-[#143628]" />
          <label htmlFor="chain" className="text-sm text-[#16221E]">Is a Chain</label>
        </div>
      </div>

      <button
        type="submit"
        data-testid="manual-submit-btn"
        disabled={saving}
        className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-white text-sm font-medium disabled:opacity-60 hover:opacity-90 transition-opacity"
        style={{ backgroundColor: saved ? "#16a34a" : "#143628" }}
      >
        {saved ? "Lead Added! Redirecting..." : saving ? "Saving..." : (<><PlusCircle size={15} /> Add Lead & Calculate Score</>)}
      </button>
    </form>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function LeadDiscovery() {
  const [tab, setTab] = useState("discover");

  return (
    <div className="p-6" style={{ backgroundColor: "#F8F9F6", minHeight: "100vh" }}>
      <div className="mb-6 animate-fade-in">
        <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-1" style={{ letterSpacing: '0.2em' }}>Add Leads</p>
        <h1 className="text-2xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
          Lead Discovery
        </h1>
        <p className="text-sm text-[#5C736A] mt-1">Search HORECA businesses, upload CSV, or add leads manually</p>
      </div>

      <div className="bg-white border border-[#DCE1D9] rounded-xl overflow-hidden animate-fade-in animate-fade-in-delay-1">
        {/* Tab bar */}
        <div className="border-b border-[#DCE1D9] px-4 flex gap-0">
          <TabButton active={tab === "discover"} onClick={() => setTab("discover")} testId="tab-discover">
            Discover via API
          </TabButton>
          <TabButton active={tab === "csv"} onClick={() => setTab("csv")} testId="tab-csv">
            CSV Upload
          </TabButton>
          <TabButton active={tab === "manual"} onClick={() => setTab("manual")} testId="tab-manual">
            Manual Entry
          </TabButton>
        </div>

        {/* Tab content */}
        <div className="p-6">
          {tab === "discover" && <DiscoverTab />}
          {tab === "csv" && <CSVTab />}
          {tab === "manual" && <ManualTab />}
        </div>
      </div>
    </div>
  );
}
