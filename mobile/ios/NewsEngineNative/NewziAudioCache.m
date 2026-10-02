#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <React/RCTBridgeModule.h>

static NSString *NewziAudioKey(NSString *url) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  NSData *urlData = [url dataUsingEncoding:NSUTF8StringEncoding];
  CC_SHA256(urlData.bytes, (CC_LONG)urlData.length, digest);
  NSMutableString *key = [NSMutableString string];
  for (int index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) [key appendFormat:@"%02x", digest[index]];
  return key;
}

@interface NewziAudioCache : NSObject <RCTBridgeModule>
@end

@implementation NewziAudioCache

RCT_EXPORT_MODULE()

RCT_EXPORT_METHOD(download:(NSString *)url
                  token:(NSString *)token
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  NSURL *remote = [NSURL URLWithString:url];
  if (!remote || ![@[@"http", @"https"] containsObject:remote.scheme.lowercaseString] || token.length == 0) {
    reject(@"AUDIO_DOWNLOAD_FAILED", @"Invalid audio request", nil);
    return;
  }
  NSString *key = NewziAudioKey(url);
  NSString *directory = [NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:@"newzi-audio"];
  [[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  for (NSString *extension in @[@"wav", @"mp3", @"m4a", @"aac"]) {
    NSString *cached = [directory stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.%@", key, extension]];
    NSDictionary *attributes = [[NSFileManager defaultManager] attributesOfItemAtPath:cached error:nil];
    if ([attributes[NSFileSize] unsignedLongLongValue] > 0) {
      resolve(cached);
      return;
    }
  }
  NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:remote];
  [request setValue:[@"Bearer " stringByAppendingString:token] forHTTPHeaderField:@"Authorization"];
  request.timeoutInterval = 120;
  [[[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    NSInteger status = [(NSHTTPURLResponse *)response statusCode];
    if (error || status != 200 || data.length == 0) {
      reject(@"AUDIO_DOWNLOAD_FAILED", [NSString stringWithFormat:@"Audio HTTP %ld", (long)status], error);
      return;
    }
    NSString *mime = response.MIMEType.lowercaseString;
    NSString *extension = [@[@"audio/mpeg", @"audio/mp3"] containsObject:mime] ? @"mp3" :
      ([@[@"audio/mp4", @"audio/x-m4a"] containsObject:mime] ? @"m4a" :
      ([mime isEqualToString:@"audio/aac"] ? @"aac" : @"wav"));
    NSString *destination = [directory stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.%@", key, extension]];
    NSError *writeError = nil;
    if (![data writeToFile:destination options:NSDataWritingAtomic error:&writeError]) {
      reject(@"AUDIO_DOWNLOAD_FAILED", @"Audio cache write failed", writeError);
      return;
    }
    resolve(destination);
  }] resume];
}

RCT_EXPORT_METHOD(savePosition:(NSString *)url seconds:(nonnull NSNumber *)seconds)
{
  [[NSUserDefaults standardUserDefaults] setDouble:seconds.doubleValue forKey:[@"newzi-audio-" stringByAppendingString:NewziAudioKey(url)]];
}

RCT_EXPORT_METHOD(getPosition:(NSString *)url
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  resolve(@([[NSUserDefaults standardUserDefaults] doubleForKey:[@"newzi-audio-" stringByAppendingString:NewziAudioKey(url)]]));
}

RCT_EXPORT_METHOD(clear)
{
  NSString *directory = [NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:@"newzi-audio"];
  [[NSFileManager defaultManager] removeItemAtPath:directory error:nil];
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  for (NSString *key in defaults.dictionaryRepresentation.allKeys) {
    if ([key hasPrefix:@"newzi-audio-"]) [defaults removeObjectForKey:key];
  }
}

@end
