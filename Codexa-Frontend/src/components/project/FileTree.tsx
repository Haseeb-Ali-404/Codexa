import { buildFileTree } from "./fileTreeUtils";
import { FolderNode } from "./FolderNode";

interface ProjectFile {
  _id: string;
  path: string;
  content: string;
  language?: string;
}

interface FileTreeProps {
  files: ProjectFile[];
  onFileSelect: (file: ProjectFile) => void;
}

export function FileTree({ files, onFileSelect }: FileTreeProps) {
  const tree = buildFileTree(files);

  return (
    <div className="text-sm">
      {tree.map((node) => (
        <FolderNode
          key={node.path}
          node={node}
          onFileSelect={onFileSelect}
        />
      ))}
    </div>
  );
}
