import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Download, ExternalLink, Calendar, Hash, HardDrive, RefreshCcw, CheckCircle, SearchCode } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';

import { Album } from '@/lib/types';

interface AlbumCardProps {
  album: Album;
  isSelected: boolean;
  onSelect: (appId: string, checked: boolean) => void;
  onDownload: (appId: string) => void;
  onInspect: (album: Album) => void;
  onReprocess?: (appId: string) => void;
  onApprove?: (appId: string) => void;
  status: 'archive' | 'review';
}

export function AlbumCard({ 
  album, 
  isSelected, 
  onSelect, 
  onDownload, 
  onInspect, 
  onReprocess, 
  onApprove,
  status 
}: AlbumCardProps) {
  
  const formatSize = (bytes: number) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const isReview = status === 'review';

  return (
    <Card className={cn(
      "bg-slate-900/40 border-slate-800 hover:border-slate-700 transition-all group relative",
      isSelected && "border-blue-500/50 bg-blue-500/5",
      isReview && !isSelected && "border-amber-900/30 hover:border-amber-700/50"
    )}>
      <div className="absolute top-4 left-4 z-10">
        <Checkbox 
          checked={isSelected} 
          onChange={(e) => onSelect(album.app_id, (e.target as HTMLInputElement).checked)}
        />
      </div>

      <CardHeader className="pb-3 pl-12">
        <div className="flex justify-between items-start mb-2">
          <Badge variant="outline" className={cn(
            "text-[10px] font-mono border-slate-700 bg-slate-950 text-slate-400",
            isReview && "border-amber-900/50 text-amber-500"
          )}>
            ID: {album.app_id}
          </Badge>
          <div className="flex gap-2">
            {album.vgmdb_url && (
              <a href={album.vgmdb_url} target="_blank" rel="noreferrer" className="text-slate-500 hover:text-blue-400 transition-colors">
                <ExternalLink size={14} />
              </a>
            )}
            <button onClick={() => onInspect(album)} className="text-slate-500 hover:text-emerald-400 transition-colors">
              <SearchCode size={14} />
            </button>
          </div>
        </div>
        <CardTitle className={cn(
          "text-lg leading-tight group-hover:text-blue-400 transition-colors",
          isReview && "group-hover:text-amber-400"
        )}>
          {album.name}
        </CardTitle>
        <CardDescription className="text-slate-500 text-xs truncate">
          {album.developer || 'Unknown Developer'}
        </CardDescription>
      </CardHeader>

      <CardContent className="pb-4 pl-12">
        <div className="grid grid-cols-2 gap-y-3">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Hash size={14} className="text-slate-600" />
            <span>{album.track_count} Tracks</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <HardDrive size={14} className="text-slate-600" />
            <span>{formatSize(album.size_bytes)}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Calendar size={14} className="text-slate-600" />
            <span>{album.processed_at ? format(new Date(album.processed_at), 'yyyy/MM/dd') : 'N/A'}</span>
          </div>
        </div>
      </CardContent>

      <CardFooter className="pt-0 flex flex-col gap-2">
        <div className="flex w-full gap-2">
          {isReview && onApprove && (
            <Button 
              onClick={() => onApprove(album.app_id)}
              className="flex-1 gap-2 bg-emerald-900/20 hover:bg-emerald-600 text-emerald-500 hover:text-white border-emerald-900/30 transition-all"
              variant="outline"
              size="sm"
            >
              <CheckCircle size={14} />
              Approve
            </Button>
          )}
          {onReprocess && (
            <Button 
              onClick={() => onReprocess(album.app_id)}
              className="flex-1 gap-2 bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white border-slate-700 transition-all"
              variant="outline"
              size="sm"
            >
              <RefreshCcw size={14} />
              Retry
            </Button>
          )}
        </div>
        <Button 
          onClick={() => onDownload(album.app_id)} 
          className={cn(
            "w-full gap-2 bg-slate-800 hover:bg-blue-600 text-slate-200 hover:text-white transition-all border-slate-700",
            isReview && "hover:bg-amber-600"
          )}
          variant="outline"
          size="sm"
        >
          <Download size={16} />
          Download ZIP
        </Button>
      </CardFooter>
    </Card>
  );
}
