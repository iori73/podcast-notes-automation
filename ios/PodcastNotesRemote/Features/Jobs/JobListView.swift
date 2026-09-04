import SwiftUI

struct JobListView: View {
    @Environment(AppSettings.self) private var settings
    @Environment(JobsModel.self) private var jobs

    var body: some View {
        NavigationStack {
            Group {
                if !settings.isConfigured {
                    ContentUnavailableView(
                        "未設定です",
                        systemImage: "gearshape",
                        description: Text("設定でサーバの URL とトークンを入力してください。")
                    )
                } else if let error = jobs.loadError, jobs.jobs.isEmpty {
                    ContentUnavailableView(
                        "接続できません",
                        systemImage: "wifi.exclamationmark",
                        description: Text(error)
                    )
                } else if jobs.jobs.isEmpty {
                    ContentUnavailableView(
                        "まだ履歴はありません",
                        systemImage: "list.bullet.rectangle",
                        description: Text("「依頼」タブから Spotify URL を送ってください。")
                    )
                } else {
                    List {
                        ForEach(jobs.jobs) { job in
                            NavigationLink(value: job) {
                                JobRow(job: job)
                            }
                        }
                    }
                }
            }
            .navigationTitle("履歴")
            .navigationDestination(for: Job.self) { JobDetailView(job: $0) }
            .refreshable { await jobs.refresh() }
            .task {
                guard settings.isConfigured else { return }
                await jobs.refresh()
                jobs.startPolling()
            }
        }
    }
}
