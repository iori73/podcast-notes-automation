import SwiftUI

struct RootView: View {
    @Binding var incomingURL: String?

    @Environment(AppSettings.self) private var settings
    @Environment(JobsModel.self) private var jobs
    @Environment(\.scenePhase) private var scenePhase

    @State private var selectedTab = Tab.submit

    enum Tab: Hashable {
        case submit, jobs, settings
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            SubmitView(incomingURL: $incomingURL)
                .tabItem { Label("依頼", systemImage: "paperplane") }
                .tag(Tab.submit)

            JobListView()
                .tabItem { Label("履歴", systemImage: "list.bullet.rectangle") }
                .tag(Tab.jobs)

            SettingsView()
                .tabItem { Label("設定", systemImage: "gearshape") }
                .tag(Tab.settings)
        }
        .onChange(of: incomingURL) { _, newValue in
            if newValue != nil { selectedTab = .submit }
        }
        .onChange(of: scenePhase) { _, phase in
            // バックグラウンドで無駄にポーリングしない
            switch phase {
            case .active:
                if settings.isConfigured { jobs.startPolling() }
            default:
                jobs.stopPolling()
            }
        }
        .task {
            if !settings.isConfigured { selectedTab = .settings }
        }
    }
}
