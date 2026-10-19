#import <React/RCTBridgeModule.h>
#import <React/RCTEventEmitter.h>

// Exposes NewziWidgetBridge.swift to JavaScript as NativeModules.NewziWidgets.
@interface RCT_EXTERN_MODULE(NewziWidgets, RCTEventEmitter)
RCT_EXTERN_METHOD(setData:(NSString *)json)
RCT_EXTERN_METHOD(liveActivitiesEnabled:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject)
RCT_EXTERN_METHOD(observeLiveActivities)
RCT_EXTERN_METHOD(startMatch:(NSString *)json resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject)
RCT_EXTERN_METHOD(endMatch:(nonnull NSNumber *)matchId)
@end
