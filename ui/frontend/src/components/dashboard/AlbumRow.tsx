import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Download, ExternalLink, HardDrive, RefreshCcw, CheckCircle, SearchCode, Music } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';

import { Album } from '@/lib/types';

interface AlbumRowProps {
  album: Album;
  isSelected: boolean;
  onSelect: (appId: string, checked: boolean) => void;
  onDownload: (appId: string) => void;
  onInspect: (album: Album) => void;
  onReprocess?: (appId: string) => void;
  onApprove?: (appId: string) => void;
  status: 'archive' | 'review';
}

export function AlbumRow({ 
  album, 
  isSelected, 
  onSelect, 
  onDownload, 
  onInspect, 
  onReprocess, 
  onApprove,
  status 
}: AlbumRowProps) {
  
  const formatSize = (bytes: number) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const isReview = status === 'review';

  return (
    <tr className={cn(
      "group border-b border-slate-800/60 hover:bg-slate-800/40 transition-all duration-200",
      isSelected ? "bg-blue-500/10" : "bg-transparent"
    )}>
      <td className="py-4 pl-4 w-12">
        <div className="flex items-center justify-center">
          <Checkbox 
            checked={isSelected} 
            onChange={(e) => onSelect(album.app_id, (e.target as HTMLInputElement).checked)}
            className="h-5 w-5 border-slate-600 bg-slate-800"
          />
        </div>
      </td>
      <td className="py-4 px-3">
        <div className="flex flex-col gap-1">
          <span className={cn(
            "font-bold text-[15px] transition-colors",
            isReview ? "text-amber-400" : "text-slate-100",
            "group-hover:text-white"
          )}>
            {album.name}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold text-slate-500 bg-slate-800/50 px-1.5 py-0.5 rounded border border-slate-700/50">
              {album.app_id}
            </span>
            <span className="text-[10px] text-slate-600">•</span>
            <span className="text-[11px] text-slate-400 truncate max-w-[250px]">{album.developer || 'Unknown'}</span>
          </div>
        </div>
      </td>
      <td className="py-4 px-2 text-center">
        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-300">
            <Music size={14} className="text-slate-500" />
            <span>{album.track_count}</span>
          </div>
        </div>
      </td>
      <td className="py-4 px-2 text-center">
        <div className="flex items-center justify-center gap-1.5 text-xs font-medium text-slate-300">
          <HardDrive size={14} className="text-slate-500" />
          <span>{formatSize(album.size_bytes)}</span>
        </div>
      </td>
      <td className="py-4 px-2 text-center text-[11px] font-mono text-slate-400">
        {album.processed_at ? format(new Date(album.processed_at), 'yyyy-MM-dd HH:mm') : 'N/A'}
      </td>
      <td className="py-4 px-4 text-right">
        <div className="flex items-center justify-end gap-3">
          {/* Action Icons */}
          <div className="flex items-center gap-1.5 mr-2 pr-3 border-r border-slate-800">
            {album.vgmdb_url && (
              <a 
                href={album.vgmdb_url} 
                target="_blank" 
                rel="noreferrer" 
                className="p-2 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 transition-all"
                title="View on VGMdb"
              >
                <ExternalLink size={18} />
              </a>
            )}
            <button 
              onClick={() => onInspect(album)} 
              className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all border border-transparent hover:border-emerald-500/20"
              title="Inspect Metadata"
            >
              <SearchCode size={18} />
            </button>
          </div>

          {/* Workflow Buttons */}
          <div className="flex items-center gap-2">
            {isReview && onApprove && (
              <Button 
                onClick={() => onApprove(album.app_id)}
                className="h-8 px-3 gap-2 bg-emerald-600/10 hover:bg-emerald-600 text-emerald-400 hover:text-white border-emerald-500/20 hover:border-emerald-500 transition-all text-[11px] font-bold uppercase tracking-tight"
                variant="outline"
              >
                <CheckCircle size={14} />
                Approve
              </Button>
            )}
            {onReprocess && (
              <Button 
                onClick={() => onReprocess(album.app_id)}
                className="h-8 px-3 gap-2 bg-slate-800/50 hover:bg-indigo-600 text-slate-300 hover:text-white border-slate-700 transition-all text-[11px] font-bold uppercase tracking-tight"
                variant="outline"
              >
                <RefreshCcw size={14} />
                Retry
              </Button>
            )}
            <Button 
              onClick={() => onDownload(album.app_id)} 
              className={cn(
                "h-8 px-3 gap-2 transition-all border text-[11px] font-bold uppercase tracking-tight",
                isReview 
                  ? "bg-amber-600/10 hover:bg-amber-600 text-amber-500 hover:text-white border-amber-500/20 hover:border-amber-500" 
                  : "bg-blue-600/10 hover:bg-blue-600 text-blue-400 hover:text-white border-blue-500/20 hover:border-blue-500"
              )}
              variant="outline"
            >
              <Download size={14} />
              ZIP
            </Button>
          </div>
        </div>
      </td>
    </tr>
  );
}
