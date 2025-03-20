function(source_repo, source_target_revision) {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "3-tor-snowflake",
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "3",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: source_repo,
            targetRevision: source_target_revision,
            path: "manifests/tor-snowflake",
        },
        destination: {
            server: "https://kubernetes.default.svc",
            namespace: "torproject",
        },
        syncPolicy: {
            automated: {
                selfHeal: true,
            },
        },
    },
}
