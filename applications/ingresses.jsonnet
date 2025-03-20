function(source_repo, source_target_revision) 

local namespaces = ["argocd", "kubetail-system", "longhorn-system"];

local appSpec(namespace, repo, revision) = {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "ingresses-" + namespace,
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "4",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: repo,
            targetRevision: revision,
            path: "manifests/ingresses/" + namespace,
        },
        destination: {
            server: "https://kubernetes.default.svc",
            namespace: namespace,
        },
        syncPolicy: {
            automated: {
                selfHeal: true,
            },
        },
    },
};

[appSpec(n, source_repo, source_target_revision) for n in namespaces]
