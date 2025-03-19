function(source_repo, source_target_revision) {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "tor-snowflake",
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
    },
    spec: {
        project: "app-nippon-koku",
        source: {
            repoURL: source_repo,
            targetRevision: source_target_revision,
            path: "application/tor-snowflake",
        },
        destination: {
            server: "https://kubernetes.default.svc",
            namespace: "torproject",
        },
    },
}
