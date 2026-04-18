import { useQuery } from '@tanstack/react-query';
import { fetchPipeline } from '@/lib/api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';

function StateBadge({ state }: { state: string }) {
  switch (state.toUpperCase()) {
    case 'RUNNING':
      return <Badge variant="running">Running</Badge>;
    case 'COMPLETED':
      return <Badge variant="success">Completed</Badge>;
    case 'FAILED':
      return <Badge variant="destructive">Failed</Badge>;
    case 'SCHEDULED':
      return <Badge variant="waiting">Scheduled</Badge>;
    default:
      return <Badge variant="outline">{state}</Badge>;
  }
}

export default function PipelinePage() {
  const { data: runs, isLoading } = useQuery({
    queryKey: ['pipeline'],
    queryFn: fetchPipeline,
    refetchInterval: 3000,
  });

  if (isLoading) return <div className="animate-pulse">Loading pipeline data...</div>;

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/50">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Flow Run Name</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Started</TableHead>
            <TableHead className="text-right">Parameters</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.isArray(runs) && runs.map((run: any) => (
            <TableRow key={run.id}>
              <TableCell className="font-mono text-xs">{run.name}</TableCell>
              <TableCell>
                <StateBadge state={run.state_name} />
              </TableCell>
              <TableCell className="text-slate-400 text-xs">
                {run.start_time ? formatDistanceToNow(new Date(run.start_time), { addSuffix: true }) : 'Pending'}
              </TableCell>
              <TableCell className="text-right font-mono text-[10px] text-slate-500">
                {JSON.stringify(run.parameters).substring(0, 50)}...
              </TableCell>
            </TableRow>
          ))}
          {(!runs || runs.length === 0) && (
            <TableRow>
              <TableCell colSpan={4} className="h-24 text-center text-slate-500">
                No active flow runs found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
