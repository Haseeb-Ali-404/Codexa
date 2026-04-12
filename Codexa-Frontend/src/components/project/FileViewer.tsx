// interface FileViewerProps {
//   file: {
//     path: string;
//     content: string;
//     language?: string;
//   } | null;
// }

// export function FileViewer({ file }: FileViewerProps) {
//   if (!file) {
//     return (
//       <div className="h-full flex items-center justify-center text-muted-foreground">
//         Select a file to view its contents
//       </div>
//     );
//   }

//   return (
//     <pre className="h-full overflow-auto p-4 text-sm bg-black text-green-400">
//       {file.content}
//     </pre>
//   );
// }
