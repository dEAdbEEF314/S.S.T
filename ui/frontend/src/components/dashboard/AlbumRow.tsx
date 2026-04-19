import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Download, ExternalLink, HardDrive, RefreshCcw, CheckCircle, SearchCode, Music } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';

interface AlbumRowProps {
  album: any;
  isSelected: boolean;
  onSelect: (appId: string, checked: boolean) => void;
  onDownload: (appId: string) => void;
  onInspect: (album: any) => void;
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
      "group border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors",
      isSelected && "bg-blue-500/5"
    )}>
      <td className="py-4 pl-4 w-10">
        <Checkbox 
          checked={isSelected} 
          onChange={(e) => onSelect(album.app_id, (e.target as HTMLInputElement).checked)}
        />
      </td>
      <td className="py-4 px-2">
        <div className="flex flex-col gap-0.5">
          <span className={cn(
            "font-bold text-slate-100 group-hover:text-blue-400 transition-colors",
            isReview && "group-hover:text-amber-400"
          )}>
            {album.name}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-slate-500">ID: {album.app_id}</span>
            <span className="text-[10px] text-slate-600">•</span>
            <span className="text-[10px] text-slate-500 truncate max-w-[200px]">{album.developer || 'Unknown'}</span>
          </div>
        </div>
      </td>
      <td className="py-4 px-2 text-center">
        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Music size={12} className="text-slate-600" />
            <span>{album.track_count}</span>
          </div>
        </div>
      </td>
      <td className="py-4 px-2 text-center">
        <div className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <HardDrive size={12} className="text-slate-600" />
          <span>{formatSize(album.size_bytes)}</span>
        </div>
      </td>
      <td className="py-4 px-2 text-center text-xs text-slate-500">
        {album.processed_at ? format(new Date(album.processed_at), 'yyyy/MM/dd HH:mm') : 'N/A'}
      </td>
      <td className="py-4 px-4 text-right">
        <div className="flex items-center justify-end gap-2">
          {/* Action Icons */}
          <div className="flex items-center gap-1 mr-2 px-2 border-r border-slate-800">
            {album.vgmdb_url && (
              <a 
                href={album.vgmdb_url} 
                target="_blank" 
                rel="noreferrer" 
                className="p-1.5 rounded-md text-slate-500 hover:text-blue-400 hover:bg-slate-800 transition-all"
                title="View on VGMdb"
              >
                <ExternalLink size={16} />
              </a>
            )}
            <button 
              onClick={() => onInspect(album)} 
              className="p-1.5 rounded-md text-slate-500 hover:text-emerald-400 hover:bg-slate-800 transition-all"
              title="Inspect Metadata"
            >
              <SearchCode size={16} />
            </button>
          </div>

          {/* Workflow Buttons */}
          <div className="flex items-center gap-2">
            {isReview && onApprove && (
              <Button 
                onClick={() => onApprove(album.app_id)}
                className="h-8 px-3 gap-2 bg-emerald-900/20 hover:bg-emerald-600 text-emerald-500 hover:text-white border-emerald-900/30 transition-all text-xs"
                variant="outline"
              >
                <CheckCircle size={14} />
                Approve
              </Button>
            )}
            {onReprocess && (
              <Button 
                onClick={() => onReprocess(album.app_id)}
                className="h-8 px-3 gap-2 bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white border-slate-700 transition-all text-xs"
                variant="outline"
              >
                <RefreshCcw size={14} />
                Retry
              </Button>
            )}
            <Button 
              onClick={() => onDownload(album.app_id)} 
              className={cn(
                "h-8 px-3 gap-2 bg-slate-800 hover:bg-blue-600 text-slate-200 hover:text-white transition-all border-slate-700 text-xs",
                isReview && "hover:bg-amber-600"
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
