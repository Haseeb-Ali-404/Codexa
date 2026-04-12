export function buildFileTree(files: any[]) {
  const root: any[] = [];

  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;

    parts.forEach((part, index) => {
      let node = current.find((n) => n.name === part);

      if (!node) {
        node = {
          name: part,
          path: parts.slice(0, index + 1).join("/"),
          isFile: index === parts.length - 1,
          children: [],
        };
        current.push(node);
      }

      if (index === parts.length - 1) {
        node.file = file;
        node.isFile = true;
      }

      current = node.children;
    });
  }

  return root;
}
