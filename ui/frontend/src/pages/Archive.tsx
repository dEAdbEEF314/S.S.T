import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAlbums, bulkDeleteAlbums, reprocessAlbum } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { AlbumRow } from '@/components/dashboard/AlbumRow';
import { Music, Trash2, Search, X, Code, Download } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';

export default function ArchivePage() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [inspectingAlbum, setInspectingAlbum] = useState<any | null>(null);

  const { data: albums, isLoading, error } = useQuery({
    queryKey: ['albums', 'archive'],
    queryFn: () => fetchAlbums('archive'),
    refetchInterval: 30000,
  });

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => bulkDeleteAlbums('archive', ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['albums', 'archive'] });
      setSelectedIds(new Set());
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: (id: string) => reprocessAlbum('archive', id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['albums', 'archive'] });
    },
  });

  const filteredAlbums = useMemo(() => {
    if (!albums) return [];
    return albums.filter((a: any) => 
      a.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
      a.app_id.toString().includes(searchTerm)
    );
  }, [albums, searchTerm]);

  const handleSelect = (appId: string, checked: boolean) => {
    const next = new Set(selectedIds);
    if (checked) next.add(appId);
    else next.delete(appId);
    setSelectedIds(next);
  };

  const handleSelectAll = () => {
    if (selectedIds.size === filteredAlbums.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredAlbums.map((a: any) => a.app_id)));
    }
  };

  const handleBulkDelete = () => {
    if (window.confirm(`Delete ${selectedIds.size} albums from S3? This cannot be undone.`)) {
      deleteMutation.mutate(Array.from(selectedIds));
    }
  };

  const handleDownload = (appId: string) => {
    window.location.href = `/download/archive/${appId}`;
  };

  if (isLoading) return <div className="flex items-center justify-center h-64 animate-pulse text-slate-500">Loading archived albums...</div>;
  if (error) return <div className="text-red-400 p-4 border border-red-900/50 bg-red-900/10 rounded-lg">Error loading albums: {(error as any).message}</div>;

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Global Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Archived Albums</h1>
          <p className="text-slate-400 text-sm">Successfully identified and tagged soundtracks.</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
            <input 
              type="text" 
              placeholder="Search albums..." 
              className="bg-slate-900 border border-slate-800 rounded-lg py-2 pl-10 pr-4 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50 transition-colors w-64"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          
          <Button 
            variant="destructive" 
            size="sm" 
            className="gap-2"
            onClick={handleBulkDelete}
            disabled={selectedIds.size === 0 || deleteMutation.isPending}
          >
            <Trash2 size={16} />
            Delete ({selectedIds.size})
          </Button>
        </div>
      </div>

      {/* Table Container */}
      <div className="bg-slate-900/20 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead className="bg-slate-900/50 border-b border-slate-800">
            <tr>
              <th className="py-3 pl-4 w-10">
                <Checkbox 
                  checked={selectedIds.size === filteredAlbums.length && filteredAlbums.length > 0}
                  onChange={handleSelectAll}
                />
              </th>
              <th className="py-3 px-2 text-xs font-bold text-slate-500 uppercase tracking-wider">Album / App ID</th>
              <th className="py-3 px-2 text-xs font-bold text-slate-500 uppercase tracking-wider text-center">Tracks</th>
              <th className="py-3 px-2 text-xs font-bold text-slate-500 uppercase tracking-wider text-center">Size</th>
              <th className="py-3 px-2 text-xs font-bold text-slate-500 uppercase tracking-wider text-center">Processed At</th>
              <th className="py-3 px-4 text-xs font-bold text-slate-500 uppercase tracking-wider text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredAlbums.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-20 text-center">
                  <Music className="mx-auto h-12 w-12 text-slate-700 mb-4" />
                  <p className="text-slate-500 italic">{searchTerm ? 'No matches found.' : 'No archived albums found.'}</p>
                </td>
              </tr>
            ) : (
              filteredAlbums.map((album: any) => (
                <AlbumRow 
                  key={album.app_id} 
                  album={album}
                  status="archive"
                  isSelected={selectedIds.has(album.app_id)}
                  onSelect={handleSelect}
                  onDownload={handleDownload}
                  onInspect={setInspectingAlbum}
                  onReprocess={(id) => reprocessMutation.mutate(id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Inspector Modal (Overlay) */}
      {inspectingAlbum && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
              <div className="flex items-center gap-3">
                <Code className="text-blue-400" size={18} />
                <h3 className="font-bold text-slate-100">Metadata Inspector: {inspectingAlbum.name}</h3>
              </div>
              <button onClick={() => setInspectingAlbum(null)} className="text-slate-500 hover:text-slate-200 transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-slate-950 font-mono text-[13px]">
              <pre className="text-emerald-400 whitespace-pre-wrap">
                {JSON.stringify(inspectingAlbum.tracks || inspectingAlbum, null, 2)}
              </pre>
            </div>
            <div className="p-4 border-t border-slate-800 flex justify-end gap-3 bg-slate-900/50">
              <Button onClick={() => setInspectingAlbum(null)} variant="secondary">Close</Button>
              <Button onClick={() => handleDownload(inspectingAlbum.app_id)} className="gap-2">
                <Download size={16} /> Download ZIP
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
