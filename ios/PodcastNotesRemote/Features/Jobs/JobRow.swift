import SwiftUI

struct JobRow: View {
    let job: Job

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                StatusBadge(status: job.status)
                Text(job.kind == .episode ? "ノート生成" : "依頼")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(job.createdAt, style: .time)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(job.displayTitle)
                .font(.subheadline)
                .lineLimit(2)

            if job.kind == .episode, let prompt = job.prompt, !prompt.isEmpty {
                Label(prompt, systemImage: "plus.bubble")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 2)
    }
}

struct StatusBadge: View {
    let status: Job.Status

    var body: some View {
        Text(status.label)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }

    private var color: Color {
        switch status {
        case .queued: .gray
        case .running: .blue
        case .succeeded: .green
        case .failed: .red
        case .cancelled: .orange
        }
    }
}
