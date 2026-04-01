import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from "recharts";
import { TrendingUp, Users, Star, ArrowRight, MapPin, Trophy, Zap } from "lucide-react";

const API = `${import.meta.env.VITE_BACKEND_URL}/api`;

const SEGMENT_COLORS = {
  Hotel: "#143628", Restaurant: "#3D6B56", Cafe: "#8FA39A",
  Bakery: "#B85C38", CloudKitchen: "#D4956A", Catering: "#6B5E44",
  Mithai: "#A0522D", IceCream: "#C4878A", Unknown: "#9CA3AF"
};

const STATUS_COLORS = {
  new: "#8FA39A", contacted: "#143628", qualified: "#B85C38",
  converted: "#16a34a", lost: "#9CA3AF"
};

const priorityColor = (p) => p === "High" ? "#B85C38" : p === "Medium" ? "#143628" : "#5C736A";

function KPICard({ title, value, sub, icon: Icon, color, delay }) {
  return (
    <div
      className={`bg-white border border-[#DCE1D9] rounded-lg p-4 lead-card animate-fade-in animate-fade-in-delay-${delay}`}
      data-testid={`kpi-card-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-1" style={{ letterSpacing: '0.15em' }}>{title}</p>
          <p className="text-3xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>{value}</p>
          {sub && <p className="text-xs text-[#5C736A] mt-1">{sub}</p>}
        </div>
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: color + '18' }}>
          <Icon size={18} style={{ color }} strokeWidth={1.5} />
        </div>
      </div>
    </div>
  );
}

function ScoreBadge({ score }) {
  const color = score >= 70 ? "#143628" : score >= 40 ? "#B85C38" : "#5C736A";
  const bg = score >= 70 ? "rgba(20,54,40,0.08)" : score >= 40 ? "rgba(184,92,56,0.08)" : "rgba(92,115,106,0.08)";
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold"
      style={{ backgroundColor: bg, color }}>
      {score}
    </span>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const init = async () => {
      await axios.post(`${API}/seed-mock-data`).catch(() => {});
      const res = await axios.get(`${API}/dashboard/stats`);
      setStats(res.data);
      setLoading(false);
    };
    init();
  }, []);

  if (loading) {
    return (
      <div className="p-8 animate-pulse">
        <div className="h-8 bg-[#EAECE6] rounded w-64 mb-6" />
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-[#EAECE6] rounded-lg" />)}
        </div>
        <div className="grid grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <div key={i} className="h-52 bg-[#EAECE6] rounded-lg" />)}
        </div>
      </div>
    );
  }

  const segData = (stats?.segment_distribution || []).map(s => ({
    name: s.segment, value: s.count, color: SEGMENT_COLORS[s.segment] || "#9CA3AF"
  }));

  const cityData = (stats?.city_distribution || []).slice(0, 6);
  const statusData = (stats?.status_distribution || []);

  return (
    <div className="p-6 min-h-screen" style={{ backgroundColor: "#F8F9F6" }}>
      {/* Header */}
      <div className="mb-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-1" style={{ letterSpacing: '0.2em' }}>
              HORECA Lead Intelligence
            </p>
            <h1 className="text-2xl font-bold text-[#143628]" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
              Sales Dashboard
            </h1>
          </div>
          <button
            data-testid="discover-leads-btn"
            onClick={() => navigate("/discover")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: "#143628" }}
          >
            <Zap size={15} /> Discover New Leads
          </button>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPICard title="Total Leads" value={stats?.total_leads || 0} sub="Across all cities" icon={Users} color="#143628" delay={1} />
        <KPICard title="High Priority" value={stats?.high_priority || 0} sub="Score ≥ 70" icon={Trophy} color="#B85C38" delay={2} />
        <KPICard title="New This Week" value={stats?.new_this_week || 0} sub="Last 7 days" icon={TrendingUp} color="#3D6B56" delay={3} />
        <KPICard title="Conversion Rate" value={`${stats?.conversion_rate || 0}%`} sub={`${stats?.converted || 0} converted`} icon={Star} color="#6B8A7A" delay={4} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* City Bar Chart */}
        <div className="col-span-2 bg-white border border-[#DCE1D9] rounded-lg p-4 animate-fade-in animate-fade-in-delay-1">
          <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-4" style={{ letterSpacing: '0.15em' }}>Leads by City</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={cityData} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EDF0EA" vertical={false} />
              <XAxis dataKey="city" tick={{ fontSize: 11, fill: '#5C736A' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#5C736A' }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#fff', border: '1px solid #DCE1D9', borderRadius: 6, fontSize: 12 }}
                cursor={{ fill: 'rgba(20,54,40,0.04)' }}
              />
              <Bar dataKey="count" fill="#143628" radius={[3, 3, 0, 0]} name="Leads" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Segment Pie */}
        <div className="bg-white border border-[#DCE1D9] rounded-lg p-4 animate-fade-in animate-fade-in-delay-2">
          <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-2" style={{ letterSpacing: '0.15em' }}>By Segment</p>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={segData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} dataKey="value" paddingAngle={2}>
                {segData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 11, border: '1px solid #DCE1D9', borderRadius: 4 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1 mt-1">
            {segData.slice(0, 6).map((s, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                <span className="text-xs text-[#5C736A] truncate">{s.name}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Recent Leads */}
        <div className="col-span-2 bg-white border border-[#DCE1D9] rounded-lg p-4 animate-fade-in animate-fade-in-delay-1">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs uppercase tracking-widest text-[#5C736A]" style={{ letterSpacing: '0.15em' }}>Recent Leads</p>
            <button
              data-testid="view-all-leads-btn"
              onClick={() => navigate("/leads")}
              className="flex items-center gap-1 text-xs text-[#143628] hover:opacity-70 font-medium"
            >
              View All <ArrowRight size={12} />
            </button>
          </div>
          <div className="space-y-2">
            {(stats?.recent_leads || []).map((lead, i) => (
              <div
                key={i}
                data-testid={`recent-lead-row-${i}`}
                className="lead-row flex items-center justify-between py-2 px-3 rounded-md border border-[#F0F3EF]"
                onClick={() => navigate(`/leads/${lead.id}`)}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[#16221E] truncate">{lead.business_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-[#5C736A]">{lead.segment}</span>
                    <span className="text-[#DCE1D9]">·</span>
                    <span className="flex items-center gap-0.5 text-xs text-[#5C736A]">
                      <MapPin size={10} /> {lead.city}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <ScoreBadge score={lead.ai_score} />
                  <span className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: priorityColor(lead.priority) + '18', color: priorityColor(lead.priority) }}>
                    {lead.priority}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pipeline Status */}
        <div className="bg-white border border-[#DCE1D9] rounded-lg p-4 animate-fade-in animate-fade-in-delay-2">
          <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-4" style={{ letterSpacing: '0.15em' }}>Pipeline Status</p>
          <div className="space-y-3">
            {statusData.map((s, i) => {
              const pct = Math.round((s.count / (stats?.total_leads || 1)) * 100);
              return (
                <div key={i}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-medium capitalize text-[#16221E]">{s.status}</span>
                    <span className="text-xs text-[#5C736A]">{s.count}</span>
                  </div>
                  <div className="h-1.5 bg-[#EDF0EA] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full score-bar-fill"
                      style={{ width: `${pct}%`, backgroundColor: STATUS_COLORS[s.status] || "#8FA39A" }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Top Leads */}
          <div className="mt-5">
            <p className="text-xs uppercase tracking-widest text-[#5C736A] mb-3" style={{ letterSpacing: '0.15em' }}>Top Scored</p>
            <div className="space-y-2">
              {(stats?.top_leads || []).slice(0, 4).map((lead, i) => (
                <div
                  key={i}
                  data-testid={`top-lead-${i}`}
                  className="lead-row flex items-center justify-between rounded px-2 py-1.5"
                  onClick={() => navigate(`/leads/${lead.id}`)}
                >
                  <p className="text-xs text-[#16221E] font-medium truncate flex-1">{lead.business_name}</p>
                  <ScoreBadge score={lead.ai_score} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
