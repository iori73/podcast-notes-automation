import Foundation
import Observation

/// ジョブ一覧の保持とポーリング。
@Observable
@MainActor
final class JobsModel {
    private(set) var jobs: [Job] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// 未完了のジョブがある間だけ短い間隔で見に行く。
    private static let activeInterval: Duration = .seconds(5)
    private static let idleInterval: Duration = .seconds(30)

    private let client: APIClient
    private var pollTask: Task<Void, Never>?

    init(client: APIClient = APIClient()) {
        self.client = client
    }

    var hasActiveJobs: Bool {
        jobs.contains { !$0.status.isTerminal }
    }

    func refresh() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            jobs = try await client.listJobs()
            loadError = nil
        } catch {
            loadError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    func startPolling() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refresh()
                let interval = self.hasActiveJobs ? Self.activeInterval : Self.idleInterval
                try? await Task.sleep(for: interval)
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    @discardableResult
    func submit(_ request: JobRequest) async throws -> Job {
        let job = try await client.submit(request)
        jobs.insert(job, at: 0)
        return job
    }

    func cancel(_ job: Job) async {
        _ = try? await client.cancel(id: job.id)
        await refresh()
    }
}

/// 1 件のジョブ詳細とログの追従。
@Observable
@MainActor
final class JobDetailModel {
    private(set) var job: Job
    private(set) var log: String = ""

    private let client: APIClient
    private var offset = 0
    private var task: Task<Void, Never>?

    init(job: Job, client: APIClient = APIClient()) {
        self.job = job
        self.client = client
    }

    func start() {
        guard task == nil else { return }
        task = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.tick()
                // 完了後もログを取り切るまでは 1 周多く回る
                if self.job.status.isTerminal { return }
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    func cancelJob() async {
        _ = try? await client.cancel(id: job.id)
        await tick()
    }

    private func tick() async {
        if let latest = try? await client.job(id: job.id) {
            job = latest
        }
        while let chunk = try? await client.log(id: job.id, offset: offset), !chunk.chunk.isEmpty {
            // サーバ側でログが巻き戻った場合は取り直す
            if chunk.offset < offset { log = "" }
            log += chunk.chunk
            offset = chunk.nextOffset
            if chunk.chunk.count < 1_000 { break }
        }
    }
}
