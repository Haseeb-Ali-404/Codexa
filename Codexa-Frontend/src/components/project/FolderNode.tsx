import { useState } from "react";

interface FileNode {
  name: string;
  path: string;
  isFile: boolean;
  children?: FileNode[];
  file?: any;
}

interface FolderNodeProps {
  node: FileNode;
  onFileSelect: (file: any) => void;
}

export function FolderNode({ node, onFileSelect }: FolderNodeProps) {
  const [open, setOpen] = useState(true);

  if (node.isFile) {
    return (
      <div
        className="pl-4 py-1 cursor-pointer hover:bg-muted rounded"
        onClick={() => onFileSelect(node.file)}
      >
        📄 {node.name}
      </div>
    );
  }

//   return (
//     // <div className="pl-2">
//     //   <div
//     //     className="cursor-pointer font-medium py-1"
//     //     onClick={() => setOpen(!open)}
//     //   >
//     //     📁 {node.name}
//     //   </div>

//     //   {open &&
//     //     node.children?.map((child) => (
//     //       <FolderNode
//     //         key={child.path}
//     //         node={child}
//     //         onFileSelect={onFileSelect}
//     //       />
//     //     ))}
//     // </div>
//   );
}
