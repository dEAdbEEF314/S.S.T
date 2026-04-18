import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchLLMLogs, fetchLLMLogDetail } from '@/lib/api';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Bot, User, Cpu, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';

function ChatBubble({ role, content }: { role: string, content: string }) {
  const isBot = role === 'assistant' || role === 'system';
  return (
    <div className={cn("flex gap-3 mb-4", isBot ? "flex-row" : "flex-row-reverse")}>
      <div className={cn(
        "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
        isBot ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-200"
      )}>
        {role === 'assistant' ? <Bot size={18} /> : role === 'system' ? <Cpu size={18} /> : <User size={18} />}
      </div>
      <div className={cn(
        "max-w-[80%] rounded-2xl px-4 py-2 text-sm",
        isBot ? "bg-slate-800 text-slate-100 rounded-tl-none" : "bg-blue-700 text-white rounded-tr-none"
      )}>
        <div className="font-bold text-[10px] uppercase opacity-50 mb-1">{role}</div>
        <div className="whitespace-pre-wrap font-noto leading-relaxed">{content}</div>
      </div>
    </div>
  );
}

export default function LLMLogsPage() {
  const [selectedLog, setSelectedLog] = useState<string | null>(null);

  const { data: logs } = useQuery({
    queryKey: ['llm-logs'],
    queryFn: fetchLLMLogs,
  });

  const { data: detail, isLoading: isDetailLoading } = useQuery({
    queryKey: ['llm-log-detail', selectedLog],
    queryFn: () => fetchLLMLogDetail(selectedLog!),
    enabled: !!selectedLog,
  });

  return (
    <div className="flex gap-6 h-[calc(100vh-12rem)]">
      {/* Sidebar: Log List */}
      <Card className="w-80 flex flex-col overflow-hidden border-slate-800">
        <CardHeader className="border-b border-slate-800 p-4">
          <CardTitle className="text-sm flex items-center gap-2">
            <MessageSquare size={16} /> Interactions
          </CardTitle>
        </CardHeader>
        <div className="flex-1 overflow-y-auto p-2 space-y-1 bg-slate-900/30">
          {logs?.map((log: any) => (
            <button
              key={log.id}
              onClick={() => setSelectedLog(log.id)}
              className={cn(
                "w-full text-left p-3 rounded-lg transition-all border border-transparent",
                selectedLog === log.id 
                  ? "bg-slate-800 border-slate-700 shadow-lg" 
                  : "hover:bg-slate-800/50 text-slate-400 hover:text-slate-200"
              )}
            >
              <div className="text-xs font-mono mb-1 text-blue-400">ID: {log.app_id}</div>
              <div className="text-[10px] truncate opacity-60">{log.filename}</div>
            </button>
          ))}
        </div>
      </Card>

      {/* Main: Chat View */}
      <Card className="flex-1 flex flex-col overflow-hidden border-slate-800 bg-slate-950/50">
        {!selectedLog ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-4">
            <Bot size={48} className="opacity-20" />
            <p className="text-sm italic">Select an interaction from the left to view details</p>
          </div>
        ) : isDetailLoading ? (
          <div className="flex-1 flex items-center justify-center animate-pulse">Loading conversation...</div>
        ) : (
          <>
            <CardHeader className="border-b border-slate-800 bg-slate-900/50 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-sm font-noto">{detail?.album_name || "Unknown Album"}</CardTitle>
                <div className="text-[10px] text-slate-400 mt-1 uppercase tracking-widest">{detail?.task_type}</div>
              </div>
              <Badge variant="outline" className="font-mono text-[10px]">{detail?.model}</Badge>
            </CardHeader>
            <div className="flex-1 overflow-y-auto p-6 scroll-smooth">
              {detail?.messages.map((msg: any, i: number) => (
                <ChatBubble key={i} role={msg.role} content={msg.content} />
              ))}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
