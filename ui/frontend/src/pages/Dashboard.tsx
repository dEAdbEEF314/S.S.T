import { useQuery } from '@tanstack/react-query';
import { fetchStats } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LucideIcon, Database, Activity, Archive, ClipboardCheck, Server } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

function StatCard({ title, value, icon: Icon, description }: { title: string, value: number | string, icon: LucideIcon, description: string }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="animate-pulse">Loading dashboard...</div>;

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard 
          title="Scanned" 
          value={stats?.scanned || 0} 
          icon={Database} 
          description="Total albums in ingest" 
        />
        <StatCard 
          title="Processing" 
          value={stats?.processing || 0} 
          icon={Activity} 
          description="Active Prefect flows" 
        />
        <StatCard 
          title="Archive" 
          value={stats?.archive || 0} 
          icon={Archive} 
          description="Successfully tagged" 
        />
        <StatCard 
          title="Review" 
          value={stats?.review || 0} 
          icon={ClipboardCheck} 
          description="Pending manual check" 
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle>System Health</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex items-center justify-between p-2 border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <Server className="h-5 w-5 text-emerald-500" />
                <span className="font-medium">Prefect Server</span>
              </div>
              <Badge variant="success">Operational</Badge>
            </div>
            <div className="flex items-center justify-between p-2 border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <Database className="h-5 w-5 text-emerald-500" />
                <span className="font-medium">SeaweedFS S3</span>
              </div>
              <Badge variant="success">Operational</Badge>
            </div>
            <div className="flex items-center justify-between p-2">
              <div className="flex items-center gap-3">
                <Activity className="h-5 w-5 text-emerald-500" />
                <span className="font-medium">Worker Pool</span>
              </div>
              <Badge variant="success">Ready</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
