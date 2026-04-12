import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Helmet } from "react-helmet";

const Index = () => {
  return (
    <>
      <Helmet>
        <title>CODEXA - Next-Gen AI Dashboard</title>
        <meta name="description" content="Experience the future of AI assistance with CODEXA - a beautiful, futuristic dashboard for intelligent conversations and code generation." />
      </Helmet>
      <DashboardLayout />
    </>
  );
};

export default Index;
