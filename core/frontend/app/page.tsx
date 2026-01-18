import Link from "next/link";

export default function Home() {
  return (
    <div className="p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            AI TaskManagement OS
          </h1>
          <p className="text-gray-400 text-lg">
            Hub-Spoke architecture with LBS (Load Balancing System)
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Dashboard Card */}
          <Link href="/dashboard">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 hover:border-blue-500 transition-colors cursor-pointer">
              <div className="flex items-center mb-3">
                <div className="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center mr-4">
                  <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold">LBS Dashboard</h2>
              </div>
              <p className="text-gray-400">
                View workload metrics, weekly stats, and task distribution
              </p>
            </div>
          </Link>

          {/* Projects Card */}
          <Link href="/projects">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 hover:border-cyan-500 transition-colors cursor-pointer">
              <div className="flex items-center mb-3">
                <div className="w-12 h-12 bg-cyan-500/20 rounded-lg flex items-center justify-center mr-4">
                  <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold">Projects</h2>
              </div>
              <p className="text-gray-400">
                Manage and chat with project-specific agents
              </p>
            </div>
          </Link>

          {/* Settings Card */}
          <Link href="/settings">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 hover:border-gray-500 transition-colors cursor-pointer">
              <div className="flex items-center mb-3">
                <div className="w-12 h-12 bg-gray-700/50 rounded-lg flex items-center justify-center mr-4">
                  <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37a1.724 1.724 0 002.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold">Settings</h2>
              </div>
              <p className="text-gray-400">
                Configure AI providers, microservices, and account security
              </p>
            </div>
          </Link>
        </div>

        {/* System Status */}
        <div className="mt-8 bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-3">System Status</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-gray-400 text-sm">Backend</p>
              <p className="text-green-400 font-semibold">● Running</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">Database</p>
              <p className="text-green-400 font-semibold">● Connected</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">AI Agents</p>
              <p className="text-blue-400 font-semibold">● Ready</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">Version</p>
              <p className="text-gray-300 font-semibold">MVP 0.1.0</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
